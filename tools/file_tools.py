import os
import tempfile
from pathlib import Path

from pydantic import Field

from tools.base import BaseTool, ToolArgs, ToolError, ToolResult
from tools.context import ToolContext


class ListArgs(ToolArgs):
    path: str = "."
    max_depth: int = Field(default=3, ge=0, le=20)


class ListFiles(BaseTool):
    name = "list_files"
    description = "List files within a depth and output limit; skip metadata and dependencies."
    args_schema = ListArgs

    async def execute(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        assert isinstance(args, ListArgs)
        root = context.resolve(args.path, directory=True)
        paths, truncated = context.files(root, max_depth=args.max_depth)
        selected = [
            p.relative_to(context.workspace.path).as_posix()
            for p in paths
            if len(p.relative_to(root).parts) - 1 <= args.max_depth
        ]
        limit = context.settings.max_entries
        return ToolResult(
            success=True,
            data={"files": selected[:limit]},
            truncated=truncated or len(selected) > limit,
        )


class ReadArgs(ToolArgs):
    path: str
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class ReadFile(BaseTool):
    name = "read_file"
    description = "Read bounded UTF-8 text with line numbers and a version token."
    args_schema = ReadArgs

    async def execute(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        assert isinstance(args, ReadArgs)
        if args.end_line is not None and args.end_line < args.start_line:
            raise ToolError("INVALID_RANGE", "end_line must be >= start_line")
        path = context.resolve(args.path)
        text, version = context.read(path)
        lines = text.splitlines()
        end = min(
            args.end_line or len(lines), args.start_line + context.settings.max_read_lines - 1
        )
        selected = lines[args.start_line - 1 : end]
        key = path.relative_to(context.workspace.path).as_posix()
        context.read_versions[key] = version
        return ToolResult(
            success=True,
            data={
                "path": key,
                "version": version,
                "total_lines": len(lines),
                "content": "\n".join(
                    f"{i}: {line}" for i, line in enumerate(selected, start=args.start_line)
                ),
            },
            truncated=end < min(args.end_line or len(lines), len(lines)),
        )


class EditArgs(ToolArgs):
    path: str
    old_text: str = Field(min_length=1)
    new_text: str
    version: str = Field(pattern=r"^[0-9a-f]{64}$")


class EditFile(BaseTool):
    name = "edit_file"
    description = "Replace one exact match in an inspected, unchanged UTF-8 file."
    args_schema = EditArgs

    async def execute(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        assert isinstance(args, EditArgs)
        path = context.resolve(args.path)
        key = path.relative_to(context.workspace.path).as_posix()
        text, version = context.read(path)
        if context.read_versions.get(key) != args.version:
            raise ToolError("NOT_INSPECTED", "Read this file before editing with its version")
        if version != args.version:
            raise ToolError("STALE_READ", "File changed; read it again")
        matches = text.count(args.old_text)
        if matches != 1:
            raise ToolError("MATCH_COUNT", f"Expected one exact match, found {matches}")
        updated = text.replace(args.old_text, args.new_text, 1).encode("utf-8")
        if len(updated) > context.settings.max_file_bytes:
            raise ToolError("FILE_TOO_LARGE", "Edited file exceeds configured limit")
        if b"\0" in updated:
            raise ToolError("UNSUPPORTED_FILE", "Text edits cannot introduce NUL bytes")
        if args.old_text == args.new_text:
            raise ToolError("NO_CHANGE", "Replacement makes no change")
        mode = path.stat().st_mode & 0o777
        fd, temporary_name = tempfile.mkstemp(prefix=".agenticfix-", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(mode)
            # Revalidate just before replacement; runtime serializes its own tools.
            context.resolve(args.path)
            if context.read(path)[1] != version:
                raise ToolError("STALE_READ", "File changed during edit")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        context.state.record_edit(key)
        context.read_versions.pop(key, None)
        return ToolResult(
            success=True, data={"path": key, "workspace_revision": context.state.workspace_revision}
        )
