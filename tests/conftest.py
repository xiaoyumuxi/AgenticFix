import sys

import pytest

from agent.state import AgentState
from config import Settings
from tools.context import ToolContext
from tools.factory import build_registry
from tracing.tracer import Tracer
from workspace.repository import WorkspaceManager, git


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / "sample.py").write_text("value = 1\nother = 2\n")
    (root / "test_sample.py").write_text("def test_ok():\n    assert True\n")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "fixture")
    return root


@pytest.fixture
def context(tmp_path, source):
    settings = Settings(
        _env_file=None,
        cache_dir=tmp_path / "cache",
        worktree_dir=tmp_path / "worktrees",
        runs_dir=tmp_path / "runs",
    )
    manager = WorkspaceManager(settings.cache_dir, settings.worktree_dir)
    repository = manager.prepare_repository(str(source))
    workspace = manager.create_workspace(repository, "run-1")
    state = AgentState(
        task_id="fixture",
        run_id=workspace.run_id,
        base_commit=workspace.base_commit,
        workspace_path=str(workspace.path),
    )
    return ToolContext(
        workspace=workspace,
        manager=manager,
        settings=settings,
        state=state,
        tracer=Tracer(settings.runs_dir / workspace.run_id),
        trusted_local=True,
        test_targets={"default": (sys.executable, "-m", "pytest", "-q")},
    )


@pytest.fixture
def registry(context):
    return build_registry(context)
