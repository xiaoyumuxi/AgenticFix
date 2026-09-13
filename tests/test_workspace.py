from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from workspace.repository import Repository, WorkspaceError, WorkspaceManager, git


def test_isolation_pin_duplicate_cleanup(context, source):
    manager = context.manager
    repo = Repository(context.workspace.cache_path, context.workspace.base_commit)
    second = manager.create_workspace(repo, "run-2")
    (context.workspace.path / "sample.py").write_text("changed")
    assert "value = 1" in (second.path / "sample.py").read_text()
    assert "value = 1" in (source / "sample.py").read_text()
    assert git(second.path, "rev-parse", "HEAD").decode().strip() == repo.base_commit
    assert git(second.path, "branch", "--show-current") == b""
    with pytest.raises(WorkspaceError, match="exists"):
        manager.create_workspace(repo, "run-2")
    with pytest.raises(WorkspaceError, match="Invalid"):
        manager.create_workspace(repo, "../escape")
    assert manager.cleanup_workspace(second, retain=True) is False
    assert second.path.exists()
    assert manager.cleanup_workspace(second)
    assert context.workspace.path.exists()
    with pytest.raises(WorkspaceError):
        manager.cleanup_workspace(second)
    with pytest.raises(WorkspaceError):
        manager.cleanup_workspace(replace(context.workspace, path=source))


def test_patch_complete_and_does_not_mutate_index(context):
    root = context.workspace.path
    (root / "sample.py").write_text("value = 99\n")
    (root / "test_sample.py").unlink()
    (root / "new file.py").write_text("new = True\n")
    (root / "data.bin").write_bytes(b"\0\xffbinary\0")
    (root / "executable.sh").write_text("#!/bin/sh\nexit 0\n")
    (root / "executable.sh").chmod(0o755)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "noise").write_text("noise")
    staged_before = git(root, "diff", "--cached", "--binary")
    patch = context.manager.export_patch(context.workspace, context.tracer.directory / "out.patch")
    assert git(root, "diff", "--cached", "--binary") == staged_before
    assert b"noise" not in patch.read_bytes()
    assert b"GIT binary patch" in patch.read_bytes()
    second = context.manager.create_workspace(
        Repository(context.workspace.cache_path, context.workspace.base_commit),
        "verify",
    )
    git(second.path, "apply", "--check", str(patch))
    git(second.path, "apply", "--binary", str(patch))
    assert (second.path / "sample.py").read_text() == "value = 99\n"
    assert not (second.path / "test_sample.py").exists()
    assert (second.path / "new file.py").exists()
    assert (second.path / "data.bin").read_bytes() == b"\0\xffbinary\0"
    assert (second.path / "executable.sh").stat().st_mode & 0o111
    with pytest.raises(WorkspaceError, match="outside"):
        context.manager.export_patch(context.workspace, root / "bad.patch")


def test_cache_update_and_invalid_ref(context, source):
    original = context.workspace.base_commit
    (source / "sample.py").write_text("next = True\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "next")
    updated = context.manager.prepare_repository(str(source))
    assert updated.base_commit != original
    assert git(context.workspace.path, "rev-parse", "HEAD").decode().strip() == original
    with pytest.raises(WorkspaceError):
        context.manager.prepare_repository(str(source), "missing-ref")


def test_concurrent_lifecycle(context):
    repo = Repository(context.workspace.cache_path, context.workspace.base_commit)

    def create(i):
        manager = WorkspaceManager(context.settings.cache_dir, context.settings.worktree_dir)
        return manager.create_workspace(repo, f"parallel-{i}")

    with ThreadPoolExecutor(max_workers=3) as executor:
        workspaces = list(executor.map(create, range(3)))
    assert len({w.path for w in workspaces}) == 3
    for workspace in workspaces:
        context.manager.cleanup_workspace(workspace)
    assert context.workspace.path.exists()


def test_patch_includes_staged_deletion_and_ignored_tracked_changes(context):
    root = context.workspace.path
    git(root, "rm", "sample.py")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "intentional").write_text("tracked explicitly")
    git(root, "add", "-f", "__pycache__/intentional")
    before = git(root, "diff", "--cached", "--binary")
    patch = context.manager.export_patch(
        context.workspace, context.tracer.directory / "staged.patch"
    )
    assert b"deleted file mode" in patch.read_bytes()
    assert b"tracked explicitly" in patch.read_bytes()
    assert git(root, "diff", "--cached", "--binary") == before
