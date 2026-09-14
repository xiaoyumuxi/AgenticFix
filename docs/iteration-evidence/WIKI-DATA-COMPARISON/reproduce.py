"""Replay frozen tests to expose each call's return value and input mutation; no LLM."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
COMMIT = '66f48ec0e6fbdbf6705a733bbadca87283ee5fa1'
HOOK = '''
import copy
import json
from pathlib import Path
import pytest

rows = []

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    name = 'checkout_total' if hasattr(item.module, 'checkout_total') else 'merge_intervals'
    original = getattr(item.module, name)
    def observed(*args, **kwargs):
        row = {'nodeid': item.nodeid, 'args': copy.deepcopy(args), 'kwargs': copy.deepcopy(kwargs)}
        try:
            value = original(*args, **kwargs)
            row['return'] = copy.deepcopy(value)
            return value
        except Exception as exc:
            row['exception'] = type(exc).__name__
            raise
        finally:
            row['args_after'] = copy.deepcopy(args)
            rows.append(row)
    setattr(item.module, name, observed)
    try:
        yield
    finally:
        setattr(item.module, name, original)

def pytest_sessionfinish(session, exitstatus):
    Path('observations.json').write_text(json.dumps({'exit_code': exitstatus, 'calls': rows}, indent=2))
'''


def main():
    output = {}
    for task, run in [('order_total', '002'), ('intervals', '003')]:
        output[task] = {}
        for phase in ['before', 'after']:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                archive = subprocess.check_output(['git', 'archive', COMMIT,
                    f'examples/{task}', f'validation/{task}'], cwd=ROOT)
                with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
                    stream.extractall(root, filter='data')
                target = root / 'examples' / task
                if phase == 'after':
                    patch = ROOT / f'docs/iteration-evidence/RUN-20260914-{run}/final.patch'
                    subprocess.run(['git', 'apply', str(patch)], cwd=target, check=True)
                shutil.copyfile(root / f'validation/{task}/test_acceptance.py', target / 'test_acceptance.py')
                (target / 'conftest.py').write_text(HOOK)
                env = {k: v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TMPDIR')}
                env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1',
                           PYTHONPYCACHEPREFIX=str(root / 'unused-cache'))
                process = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=target,
                    env=env, capture_output=True, text=True, timeout=60)
                observation = json.loads((target / 'observations.json').read_text())
                assert observation['exit_code'] == process.returncode
                historical = json.loads((ROOT / f'docs/iteration-evidence/RUN-20260914-{run}/summary.json').read_text())
                assert process.returncode == historical[phase]['exit_code']
                observation['pytest_output'] = process.stdout
                output[task][phase] = observation
    (Path(__file__).parent / 'observations.json').write_text(json.dumps({
        'source_commit': COMMIT, 'kind': 'Supplemental replay of frozen tests and archived patches; not original live-run return-value telemetry',
        'results': output}, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
