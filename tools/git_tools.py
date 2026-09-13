from tools.base import BaseTool, ToolArgs, ToolResult
from tools.context import ToolContext


class DiffArgs(ToolArgs):
    pass


class GitDiff(BaseTool):
    name = "git_diff"
    description = "Export a complete binary-capable patch against the immutable base commit."
    args_schema = DiffArgs

    async def execute(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        context.invalidate_external_changes(context.patch_digest())
        patch = context.manager.export_patch(
            context.workspace, context.tracer.directory / "final.patch"
        )
        with patch.open("rb") as stream:
            preview = stream.read(context.settings.max_output_bytes + 1)
        context.state.final_patch_path = str(patch)
        return ToolResult(
            success=True,
            data={
                "patch_path": str(patch),
                "base_commit": context.workspace.base_commit,
                "preview": preview[: context.settings.max_output_bytes].decode(
                    "utf-8", errors="replace"
                ),
            },
            truncated=len(preview) > context.settings.max_output_bytes,
        )
