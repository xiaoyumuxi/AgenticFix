from pydantic import Field

from sandbox.local import LocalSandbox
from tools.base import BaseTool, ToolArgs, ToolError, ToolResult
from tools.context import ToolContext


class RunTestsArgs(ToolArgs):
    target: str = "default"
    timeout: float = Field(default=60, gt=0)


class RunTests(BaseTool):
    name = "run_tests"
    description = "Run a host-configured pytest target in an explicitly trusted fixture."
    args_schema = RunTestsArgs

    async def execute(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        assert isinstance(args, RunTestsArgs)
        if not context.trusted_local:
            raise ToolError("UNTRUSTED_EXECUTION", "Docker required for external repositories")
        if args.target not in context.test_targets:
            raise ToolError("UNKNOWN_TARGET", "Test target is not configured")
        before_digest = context.patch_digest()
        context.invalidate_external_changes(before_digest)
        tested_revision = context.state.workspace_revision
        sandbox = LocalSandbox(trusted=True, max_output_bytes=context.settings.max_output_bytes)
        result = await sandbox.run(
            context.test_targets[args.target],
            context.workspace.path,
            min(args.timeout, context.settings.max_test_timeout),
        )
        if result.launch_error:
            status = "launch_error"
        elif result.timed_out:
            status = "timeout"
        else:
            status = {
                0: "passed",
                1: "failed",
                2: "interrupted",
                3: "internal_error",
                4: "usage_error",
                5: "no_tests",
            }.get(result.exit_code if result.exit_code is not None else -1, "process_error")
        after_digest = context.patch_digest()
        if after_digest != before_digest:
            context.state.workspace_revision += 1
            status = "workspace_changed"
        context.state.tested_patch_digest = before_digest
        context.state.tested_revision = tested_revision
        context.state.test_status = status
        data = result.model_dump() | {
            "status": status,
            "tested_revision": context.state.tested_revision,
            "target": args.target,
        }
        artifact = context.tracer.save_json(f"test-{context.state.total_tool_calls}.json", data)
        data["artifact"] = str(artifact)
        return ToolResult(
            success=not (result.launch_error or result.timed_out),
            data=data,
            truncated=result.truncated,
            error_code=status.upper() if result.launch_error or result.timed_out else None,
        )
