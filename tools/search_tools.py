from fnmatch import fnmatch

from pydantic import Field

from tools.base import BaseTool, ToolArgs, ToolError, ToolResult
from tools.context import ToolContext


class SearchArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=1000)
    file_pattern: str = "*"
    max_results: int = Field(default=50, ge=1, le=1000)


class SearchCode(BaseTool):
    name = "search_code"
    description = "Literal UTF-8 substring search with file glob and bounded results."
    args_schema = SearchArgs

    async def execute(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        assert isinstance(args, SearchArgs)
        paths, truncated = context.files(context.resolve(".", directory=True))
        results: list[dict[str, str | int]] = []
        skipped = 0
        scanned_bytes = 0
        for path in paths:
            name = path.relative_to(context.workspace.path).as_posix()
            if not fnmatch(name, args.file_pattern):
                continue
            try:
                context.resolve(name)
                text, _ = context.read(path)
            except ToolError:
                skipped += 1
                continue
            scanned_bytes += len(text.encode("utf-8"))
            if scanned_bytes > context.settings.max_file_bytes * 20:
                truncated = True
                break
            for number, line in enumerate(text.splitlines(), 1):
                offset = line.find(args.query)
                if offset < 0:
                    continue
                if len(results) >= min(args.max_results, context.settings.max_entries):
                    return ToolResult(
                        success=True,
                        data={"matches": results, "skipped_files": skipped},
                        truncated=True,
                    )
                left = max(0, offset - 100)
                snippet = line[left : left + 400]
                results.append({"file": name, "line": number, "snippet": snippet})
                truncated = truncated or len(snippet) < len(line)
        return ToolResult(
            success=True,
            data={"matches": results, "skipped_files": skipped},
            truncated=truncated or skipped > 0,
        )
