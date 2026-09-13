"""Host-controlled Git metadata. LocalSandbox is for trusted fixtures only."""

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock


class WorkspaceError(RuntimeError):
    pass


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> bytes:
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    clean_env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
    if env:
        clean_env.update(env)
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=cwd,
            env=clean_env,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceError(f"Git execution failed: {type(exc).__name__}") from exc
    if result.returncode:
        raise WorkspaceError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


@dataclass(frozen=True)
class Repository:
    cache_path: Path
    base_commit: str


@dataclass(frozen=True)
class Workspace:
    path: Path
    cache_path: Path
    base_commit: str
    run_id: str


class WorkspaceManager:
    def __init__(self, cache_dir: Path, worktree_dir: Path) -> None:
        self.cache_dir = cache_dir.resolve()
        self.worktree_dir = worktree_dir.resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        # Global lock makes lifecycle operations simple and deterministic in M1.
        self.lock = FileLock(str(self.cache_dir / ".metadata.lock"), timeout=60)

    def prepare_repository(self, source: str, ref: str = "HEAD") -> Repository:
        local = Path(source).expanduser()
        if local.exists():
            source = str(local.resolve())
        elif not source.startswith("https://"):
            raise WorkspaceError("Source must be a local Git repository or HTTPS URL")
        if source.startswith("https://"):
            from urllib.parse import urlsplit

            url = urlsplit(source)
            if url.username or url.password:
                raise WorkspaceError("Credentials must not be embedded in repository URLs")
        key = hashlib.sha256(source.encode()).hexdigest()[:24]
        cache = self.cache_dir / f"{key}.git"
        with self.lock:
            if not cache.exists():
                temporary = Path(tempfile.mkdtemp(prefix="clone-", dir=self.cache_dir))
                try:
                    git(
                        self.cache_dir,
                        "clone",
                        "--bare",
                        "--no-local",
                        "--",
                        source,
                        str(temporary / "repo.git"),
                    )
                    (temporary / "repo.git").rename(cache)
                finally:
                    import shutil

                    shutil.rmtree(temporary)
            else:
                git(
                    cache,
                    "fetch",
                    "--prune",
                    "origin",
                    "+refs/heads/*:refs/heads/*",
                    "+refs/tags/*:refs/tags/*",
                )
            commit = (
                git(cache, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
                .decode()
                .strip()
            )
        return Repository(cache, commit)

    def create_workspace(self, repo: Repository, run_id: str) -> Workspace:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
            raise WorkspaceError("Invalid run_id")
        if repo.cache_path.parent != self.cache_dir:
            raise WorkspaceError("Repository does not belong to this cache")
        path = self.worktree_dir / run_id
        with self.lock:
            if path.exists() or path.is_symlink():
                raise WorkspaceError(f"Workspace already exists: {run_id}")
            git(repo.cache_path, "worktree", "add", "--detach", str(path), repo.base_commit)
        return Workspace(path, repo.cache_path, repo.base_commit, run_id)

    def _validate(self, workspace: Workspace) -> None:
        if (
            workspace.path.parent != self.worktree_dir
            or workspace.path.is_symlink()
            or workspace.cache_path.parent != self.cache_dir
            or workspace.path.name != workspace.run_id
        ):
            raise WorkspaceError("Workspace does not belong to this manager")
        common = Path(
            git(workspace.path, "rev-parse", "--path-format=absolute", "--git-common-dir")
            .decode()
            .strip()
        ).resolve()
        if common != workspace.cache_path:
            raise WorkspaceError("Git metadata does not match workspace")

    def export_patch(self, workspace: Workspace, destination: Path) -> Path:
        with self.lock:
            self._validate(workspace)
            destination = destination.resolve()
            if destination.is_relative_to(workspace.path):
                raise WorkspaceError("Patch artifacts must be outside the workspace")
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Private temporary index: include untracked files without changing the real index.
            with tempfile.TemporaryDirectory(prefix="patch-", dir=self.cache_dir) as temp:
                env = {"GIT_INDEX_FILE": str(Path(temp) / "index")}
                git(workspace.path, "read-tree", workspace.base_commit, env=env)
                # Exclusions affect only untracked artifacts; tracked changes always survive.
                tracked = git(workspace.path, "ls-files", "-z").split(b"\0")
                untracked = git(
                    workspace.path, "ls-files", "--others", "--exclude-standard", "-z"
                ).split(b"\0")
                ignored = {
                    ".venv",
                    "__pycache__",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".mypy_cache",
                    "node_modules",
                    ".DS_Store",
                }
                base_paths = git(
                    workspace.path, "ls-tree", "-r", "--name-only", "-z", workspace.base_commit
                ).split(b"\0")
                candidates = set(p for p in tracked + base_paths if p)
                candidates.update(
                    p for p in untracked if p and not (set(Path(os.fsdecode(p)).parts) & ignored)
                )
                # Add explicit paths in small batches; index starts at the base commit.
                paths = [os.fsdecode(p) for p in sorted(candidates)]
                for start in range(0, len(paths), 100):
                    git(
                        workspace.path,
                        "--literal-pathspecs",
                        "add",
                        "-A",
                        "-f",
                        "--",
                        *paths[start : start + 100],
                        env=env,
                    )
                patch = git(
                    workspace.path,
                    "diff",
                    "--cached",
                    "--binary",
                    "--full-index",
                    "--no-ext-diff",
                    "--no-textconv",
                    workspace.base_commit,
                    "--",
                    env=env,
                )
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_bytes(patch)
            temporary.replace(destination)
        return destination

    def cleanup_workspace(self, workspace: Workspace, *, retain: bool = False) -> bool:
        with self.lock:
            self._validate(workspace)
            if retain:
                return False
            git(workspace.cache_path, "worktree", "remove", "--force", str(workspace.path))
        return True
