import time
from typing import Any
from uuid import uuid4

from filelock import Timeout
from pydantic import ValidationError

from tools.base import BaseTool, ToolError, ToolResult
from tools.context import ToolContext
from tracing.models import TraceEvent


class ToolRegistry:
    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.args_schema.model_json_schema(),
            }
            for t in self.tools.values()
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        async with self.context.lock:
            return await self._call(name, arguments)

    async def _call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        ctx = self.context
        if ctx.state.status != "running":
            return ToolResult(success=False, error_code="RUN_STOPPED", error="Run is not active")
        call_id = uuid4().hex
        started = time.monotonic()
        ctx.state.total_tool_calls += 1
        try:
            ctx.tracer.append(
                TraceEvent(
                    run_id=ctx.state.run_id,
                    event="tool_started",
                    call_id=call_id,
                    tool=name,
                    arguments=arguments,
                )
            )
        except (OSError, Timeout):
            ctx.state.status = "failed"
            ctx.state.stop_reason = "trace_failure"
            return ToolResult(
                success=False,
                error_code="TRACE_FAILURE",
                error="Cannot persist tool trace",
                fatal=True,
            )
        try:
            if name not in self.tools:
                raise ToolError("UNKNOWN_TOOL", "Tool is not registered")
            tool = self.tools[name]
            args = tool.args_schema.model_validate(arguments)
            result = await tool.execute(args, ctx)
        except ValidationError as exc:
            result = ToolResult(success=False, error_code="INVALID_ARGUMENTS", error=str(exc))
        except ToolError as exc:
            result = ToolResult(success=False, error_code=exc.code, error=str(exc), fatal=exc.fatal)
        except OSError as exc:
            result = ToolResult(success=False, error_code="IO_ERROR", error=type(exc).__name__)
        except Exception as exc:
            # Unexpected invariant failures stop the run, rather than silently continuing.
            result = ToolResult(
                success=False, error_code="INTERNAL_ERROR", error=type(exc).__name__, fatal=True
            )
        if result.fatal:
            ctx.state.status = "failed"
            ctx.state.stop_reason = result.error_code
        try:
            ctx.tracer.append(
                TraceEvent(
                    run_id=ctx.state.run_id,
                    event="tool_finished",
                    call_id=call_id,
                    tool=name,
                    result=result.model_dump(),
                    duration=time.monotonic() - started,
                )
            )
            ctx.tracer.save_json("state.json", ctx.state.model_dump())
        except (OSError, Timeout):
            ctx.state.status = "failed"
            ctx.state.stop_reason = "trace_failure"
            return ToolResult(
                success=False,
                error_code="TRACE_FAILURE",
                error="Cannot persist result; inspect workspace before retrying",
                fatal=True,
            )
        return result
