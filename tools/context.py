import asyncio
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from agent.state import AgentState
from config import Settings
from tools.base import ToolError
from tracing.tracer import Tracer
from workspace.repository import Workspace, WorkspaceManager

IGNORED = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}
PROTECTED = {".git", ".env"}


@dataclass
class ToolContext:
    workspace: Workspace
    manager: WorkspaceManager
    settings: Settings
    state: AgentState
    tracer: Tracer
    test_targets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    trusted_local: bool = False
    read_versions: dict[str, str] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if self.tracer.directory.is_relative_to(self.workspace.path.resolve()):
            raise ValueError("Run artifacts must be outside workspace")

    def patch_digest(self) -> str:
        path = self.manager.export_patch(self.workspace, self.tracer.directory / ".snapshot.patch")
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def invalidate_external_changes(self, digest: str) -> None:
        if self.state.tested_patch_digest and self.state.tested_patch_digest != digest:
            self.state.workspace_revision += 1
            self.state.tested_revision = None
            self.state.test_status = None
            self.state.tested_patch_digest = None

    def resolve(self, name: str, *, directory: bool = False) -> Path:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ToolError("PATH_ESCAPE", "Use a relative path within the workspace")
        if any(p in PROTECTED or p.startswith(".env.") for p in relative.parts):
            raise ToolError("PROTECTED_PATH", "Git metadata and environment files are protected")
        root = self.workspace.path.resolve()
        if root != self.workspace.path or self.workspace.path.is_symlink():
            raise ToolError("ISOLATION_FAILURE", "Workspace root changed", fatal=True)
        path = root / relative
        # Deny all symlinks rather than racing an out-of-tree target check.
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ToolError("PATH_ESCAPE", "Symlink paths are not supported")
        if not path.resolve().is_relative_to(root):
            raise ToolError("PATH_ESCAPE", "Path is outside workspace")
        if not path.exists():
            raise ToolError("NOT_FOUND", "Path does not exist")
        if directory:
            if not path.is_dir():
                raise ToolError("NOT_DIRECTORY", "Expected a directory")
        elif not path.is_file():
            raise ToolError("NOT_FILE", "Expected a regular file")
        if not directory and path.stat().st_nlink > 1:
            raise ToolError("UNSUPPORTED_FILE", "Hard-linked files are not supported")
        return path

    def read(self, path: Path) -> tuple[str, str]:
        with path.open("rb") as stream:
            raw = stream.read(self.settings.max_file_bytes + 1)
        if len(raw) > self.settings.max_file_bytes:
            raise ToolError("FILE_TOO_LARGE", "File exceeds configured limit")
        if b"\0" in raw:
            raise ToolError("UNSUPPORTED_FILE", "Binary files are not supported by text tools")
        try:
            return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()
        except UnicodeDecodeError as exc:
            raise ToolError("UNSUPPORTED_ENCODING", "Expected UTF-8 text") from exc

    def files(self, root: Path, max_depth: int | None = None) -> tuple[list[Path], bool]:
        found: list[Path] = []
        scanned = 0
        pending = [root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > self.settings.max_scan_entries:
                        return sorted(found), True
                    if (
                        entry.name in IGNORED
                        or entry.name == ".env"
                        or entry.name.startswith(".env.")
                    ):
                        continue
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if (
                            max_depth is None
                            or len(Path(entry.path).relative_to(root).parts) <= max_depth
                        ):
                            pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        found.append(Path(entry.path))
        return sorted(found), False
