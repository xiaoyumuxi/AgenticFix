"""Post-run diagnostic: preserve original patch; isolate the incorrect test input in Docker."""
import asyncio
import json
from pathlib import Path

from sandbox.docker import DockerSandbox
from workspace.repository import WorkspaceManager, git

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = Path(__file__).resolve().parent


async def main():
    summary = json.loads((ARCHIVE / 'summary.json').read_text())
    manager = WorkspaceManager(ROOT / '.cache/repositories', ROOT / '.worktrees')
    repo = manager.prepare_repository(str(ROOT / '.cache/m3-upstream'), summary['task']['base_commit'])
    work = manager.create_workspace(repo, 'diagnostic-test-expectation-011')
    directory = ROOT / 'runs/m3-development/test-expectation-011'
    box = DockerSandbox(directory)
    box.image_id = summary['agent']['environment']['image_id']
    results = {'kind': 'Post-run diagnostic, correction by evaluator, not model success',
               'image_id': box.image_id, 'base_commit': summary['task']['base_commit']}
    try:
        git(work.path, 'apply', str(ARCHIVE / 'candidate.patch'))
        command = ('python', '-m', 'pytest', '-q', '-o', 'addopts=', '-p', 'no:cacheprovider',
                   'tests/test_more.py::NumericRangeTests::test_reversed')
        results['original'] = (await box.run(command, work.path, 120)).model_dump()
        path = work.path / 'tests/test_more.py'
        old = '            ((1.0, 0.0, -1.0), []),'
        new = '            ((0.0, 1.0, -1.0), []),'
        text = path.read_text()
        assert text.count(old) == 1
        path.write_text(text.replace(old, new))
        results['correction'] = {'old': old.strip(), 'new': new.strip()}
        results['corrected'] = (await box.run(command, work.path, 120)).model_dump()
        assert results['original']['exit_code'] == 1
        assert results['corrected']['exit_code'] == 0
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'comparison.json').write_text(json.dumps(results, indent=2) + '\n')
    finally:
        manager.cleanup_workspace(work)


if __name__ == '__main__':
    asyncio.run(main())
