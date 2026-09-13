"""Compare preparation failure archives; no model request is made."""
import asyncio
import json
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

from pydantic import SecretStr

from agent.runner import run_agent
from config import Settings
from workspace.repository import git

ROOT = Path(__file__).resolve().parents[3]
OLD = '85782f9cbe66099ec4247b8080407108d75b365b'


async def main():
    module = types.ModuleType('historical_runner')
    module.__file__ = str(ROOT / 'agent/runner.py')
    exec(compile(git(ROOT, 'show', f'{OLD}:agent/runner.py'), module.__file__, 'exec'), module.__dict__)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, runner in [('before', module.run_agent), ('after', run_agent)]:
            root = Path(tmp) / name
            settings = Settings(_env_file=None, runs_dir=root / 'runs',
                                cache_dir=root / 'cache', worktree_dir=root / 'worktrees',
                                model_api_key=SecretStr('not-a-real-key'))
            with patch('workspace.repository.WorkspaceManager.prepare_repository',
                       side_effect=RuntimeError('controlled-setup-failure')):
                try:
                    await runner(settings)
                except RuntimeError:
                    pass
            directory = next((root / 'runs').iterdir())
            rows.append({'version': name, 'old_commit': OLD if name == 'before' else None,
                         'files': sorted(p.name for p in directory.glob('*.json')),
                         'has_failure_record': (directory / 'runner-error.json').exists(),
                         'has_start_snapshot': (directory / 'metadata.json').exists(),
                         'has_manifest': (directory / 'manifest.json').exists()})
    print(json.dumps(rows, indent=2))


asyncio.run(main())
