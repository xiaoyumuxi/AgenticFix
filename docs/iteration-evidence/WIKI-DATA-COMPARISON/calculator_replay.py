"""Supplemental return-value observations from archived Calculator inputs and patch."""
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = 'docs/iteration-evidence/RUN-20260914-001'
COMMIT = '1ad3fda9a588dfe181a119f3b7f9247de2f07d87'


def main():
    hook = runpy.run_path(str(Path(__file__).with_name('reproduce.py')))['HOOK']
    hook = hook.replace("name = 'checkout_total' if hasattr(item.module, 'checkout_total') else 'merge_intervals'", "name = 'add'")
    results = {}
    for phase in ['before', 'after']:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            blob = subprocess.check_output(['git', 'archive', COMMIT, EVIDENCE], cwd=ROOT)
            with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
                archive.extractall(directory, filter='data')
            evidence = directory / EVIDENCE
            target = evidence / 'fixture-source'
            shutil.copyfile(evidence / 'test_additional.py', target / 'test_additional.py')
            if phase == 'after':
                subprocess.run(['git', 'apply', str(evidence / 'final.patch')], cwd=target, check=True)
            (target / 'conftest.py').write_text(hook)
            env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TMPDIR')}
            env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1',
                       PYTHONPYCACHEPREFIX=str(directory / 'unused-cache'))
            process = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--junitxml=result.xml'],
                cwd=target, env=env, capture_output=True, text=True, timeout=60)
            observed = json.loads((target / 'observations.json').read_text())
            cases = {c.get('classname')+'::'+c.get('name'): 'failed' if c.find('failure') is not None else 'passed'
                     for c in ET.parse(target / 'result.xml').iter('testcase')}
            assert len(cases) == len(observed['calls']) == 29
            assert sum(v=='failed' for v in cases.values()) == (9 if phase=='before' else 0)
            assert process.returncode == (1 if phase=='before' else 0)
            results[phase] = observed | {'cases': cases, 'pytest_output': process.stdout}
    Path(__file__).with_name('calculator-observations.json').write_text(json.dumps({
        'archive_commit': COMMIT, 'source': EVIDENCE,
        'kind': 'Supplemental replay, not original model-run telemetry. Original additional tests were post-run checks.',
        'results': results}, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
