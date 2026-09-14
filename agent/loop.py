"""Small deterministic runtime around a provider-neutral model and existing tools."""

import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.llm import LLMClient, ModelError, ModelReply
from agent.prompts import prompt_for_environment
from tools.base import ToolResult
from tools.registry import ToolRegistry
from tracing.models import TraceEvent


class StopRun(Exception):
    pass


class AgentLoop:
    def __init__(self, client: LLMClient, registry: ToolRegistry) -> None:
        self.client = client
        self.registry = registry
        self.context = registry.context
        self.settings = self.context.settings
        self.state = self.context.state
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": prompt_for_environment(
                    self.settings.environment_prompt_version if self.context.docker else None
                ),
            },
            {"role": "user", "content": self.state.issue},
        ]
        self.actions: Counter[str] = Counter()
        self.started = 0.0

    def stop(self, reason: str) -> None:
        self.state.status = "failed"
        self.state.stop_reason = reason
        raise StopRun(reason)

    def feedback(self, text: str) -> None:
        self.messages.append({"role": "user", "content": f"Runtime observation: {text}"})

    def tool_message(self, result: ToolResult, tool_name: str | None = None) -> str:
        if (
            self.settings.compact_successful_build
            and tool_name == "build_environment"
            and result.success
            and not result.fatal
            and result.data.get("exit_code") == 0
            and not result.data.get("timed_out")
            and result.data.get("image_id")
        ):
            # Project only the model message; the registry and artifact retain the full result.
            result = result.model_copy(
                update={
                    "data": {
                        key: result.data[key]
                        for key in (
                            "exit_code",
                            "timed_out",
                            "image_id",
                            "dockerfile_sha256",
                            "duration",
                            "total_duration",
                            "cache",
                            "artifact",
                        )
                        if key in result.data
                    }
                    | {
                        "context_note": "Build succeeded. Build logs omitted from model context; "
                        "full result retained in the artifact. Run public tests to validate it."
                    },
                    "truncated": True,
                }
            )
        text = json.dumps(result.model_dump(), ensure_ascii=False)
        limit = self.settings.max_tool_message_chars
        if len(text) <= limit:
            return text
        return json.dumps(
            {
                "success": result.success,
                "error_code": result.error_code,
                "truncated": True,
                "preview": text[:limit],
                "hint": "Output shortened for model context. Use narrower read/search ranges.",
            },
            ensure_ascii=False,
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if self.state.total_tool_calls >= self.settings.max_tool_calls:
            self.stop("tool_budget")
        result = await self.registry.call(name, arguments)
        if result.fatal:
            self.stop(result.error_code or "fatal_tool_error")
        return result

    async def request(self) -> ModelReply:
        for attempt in range(self.settings.max_model_retries + 1):
            if self.state.iteration >= self.settings.max_iterations:
                self.stop("iteration_budget")
            encoded = json.dumps(
                {"messages": self.messages, "tools": self.registry.schemas()}, ensure_ascii=False
            ).encode("utf-8")
            if len(encoded) > self.settings.max_context_bytes:
                self.stop("context_budget")
            # Byte count + framing overhead is deliberately conservative, not a tokenizer.
            input_reserve = len(encoded) + 256
            remaining = self.settings.max_token_budget - self.state.total_tokens
            completion_limit = min(self.settings.max_completion_tokens, remaining - input_reserve)
            if completion_limit < 1:
                self.stop("token_budget")
            reservation = input_reserve + completion_limit
            self.state.iteration += 1
            self.state.model_requests += 1
            call_id = uuid4().hex
            start = time.monotonic()
            self.context.tracer.append(
                TraceEvent(
                    run_id=self.state.run_id,
                    event="model_started",
                    call_id=call_id,
                    tool="model",
                    arguments={
                        "iteration": self.state.iteration,
                        "reserved_tokens": reservation,
                        "context_bytes": len(encoded),
                        "input_reserve": input_reserve,
                        "remaining_budget": remaining,
                        "max_completion_tokens": completion_limit,
                    },
                )
            )
            # Charge before awaiting; a timeout/cancellation may still incur provider cost.
            self.state.estimated_tokens += reservation
            self.state.total_tokens += reservation
            self.state.unknown_usage_requests += 1
            self.persist()
            try:
                reply = await self.client.generate(
                    self.messages,
                    self.registry.schemas(),
                    completion_limit,
                )
            except ModelError as exc:
                self.context.tracer.append(
                    TraceEvent(
                        run_id=self.state.run_id,
                        event="model_failed",
                        call_id=call_id,
                        tool="model",
                        result={"error_code": exc.code, "retryable": exc.retryable},
                        duration=time.monotonic() - start,
                    )
                )
                if not exc.retryable or attempt == self.settings.max_model_retries:
                    self.stop(exc.code)
                await asyncio.sleep(self.settings.retry_delay * (2**attempt))
                continue
            if reply.usage is not None:
                self.state.estimated_tokens -= reservation
                self.state.total_tokens += reply.usage.total_tokens - reservation
                self.state.reported_tokens += reply.usage.total_tokens
                self.state.unknown_usage_requests -= 1
            self.context.tracer.append(
                TraceEvent(
                    run_id=self.state.run_id,
                    event="model_finished",
                    call_id=call_id,
                    tool="model",
                    result={"response": reply.model_dump(exclude_none=True)},
                    duration=time.monotonic() - start,
                )
            )
            if self.state.total_tokens > self.settings.max_token_budget:
                self.stop("token_budget")
            return reply
        raise AssertionError("Unreachable retry loop")

    def persist(self) -> None:
        self.context.tracer.save_json("messages.json", {"messages": self.messages})
        self.context.tracer.save_json("state.json", self.state.model_dump())

    async def drive(self) -> None:
        if self.context.docker is None:
            baseline = await self.call_tool("run_tests", {"target": "default"})
            self.feedback("Initial public test baseline: " + self.tool_message(baseline))
        else:
            self.feedback(
                "Environment is not built. Inspect project requirements, build, then test."
            )
        while True:
            reply = await self.request()
            message = reply.message.model_dump(exclude_none=True)
            if reply.finish_reason not in {"stop", "tool_calls"}:
                # Never execute arguments from a truncated or filtered completion.
                self.stop(f"model_finish_{reply.finish_reason}")
            self.messages.append(message)
            calls = reply.message.tool_calls or []
            if calls:
                for call in calls:
                    try:
                        args = json.loads(call.function.arguments)
                        if not isinstance(args, dict):
                            raise ValueError("Arguments must be an object")
                    except (ValueError, TypeError):
                        result = ToolResult(
                            success=False,
                            error_code="INVALID_JSON",
                            error="Function arguments must be a JSON object",
                        )
                        # Invalid model attempts still consume the tool-call budget.
                        if self.state.total_tool_calls >= self.settings.max_tool_calls:
                            self.stop("tool_budget")
                        self.state.total_tool_calls += 1
                        self.context.tracer.append(
                            TraceEvent(
                                run_id=self.state.run_id,
                                event="tool_rejected",
                                call_id=call.id,
                                tool=call.function.name,
                                result=result.model_dump(),
                            )
                        )
                    else:
                        signature = json.dumps(
                            [self.state.workspace_revision, call.function.name, args],
                            sort_keys=True,
                        )
                        self.actions[signature] += 1
                        if self.actions[signature] > self.settings.max_repeated_actions:
                            self.stop("repeated_action")
                        result = await self.call_tool(call.function.name, args)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": self.tool_message(result, call.function.name),
                        }
                    )
                self.persist()
                continue
            if not reply.message.content or not reply.message.content.strip():
                self.feedback("Empty response. Choose an appropriate tool or explain the result.")
                self.persist()
                continue
            # A plain final is only a request; runtime always checks its configured default target.
            validation = await self.call_tool("run_tests", {"target": "default"})
            if not self.state.current_tests_passed:
                self.feedback(
                    "Completion rejected; current public verification: "
                    + self.tool_message(validation)
                )
                self.persist()
                continue
            patch_result = await self.call_tool("git_diff", {})
            if not patch_result.success or not self.state.current_tests_passed:
                self.feedback("Completion rejected: patch export or current-version check failed.")
                continue
            patch = Path(patch_result.data["patch_path"])
            if not patch.stat().st_size:
                self.feedback("Completion rejected: empty patch. Investigate and fix the issue.")
                continue
            self.state.status = "completed"
            self.state.stop_reason = "public_tests_passed"
            self.state.final_answer = reply.message.content
            return

    async def run(self) -> dict[str, Any]:
        self.started = time.monotonic()
        artifact_errors: list[str] = []
        try:
            async with asyncio.timeout(self.settings.max_run_duration):
                await self.drive()
        except StopRun:
            pass
        except TimeoutError:
            self.state.status = "failed"
            self.state.stop_reason = "run_timeout"
        except asyncio.CancelledError:
            self.state.status = "failed"
            self.state.stop_reason = "cancelled"
            raise
        except Exception as exc:
            self.state.status = "failed"
            self.state.stop_reason = f"runtime_error:{type(exc).__name__}"
        finally:
            self.state.duration = time.monotonic() - self.started
            # Artifact export is housekeeping, not another model-directed tool action.
            try:
                path = self.context.manager.export_patch(
                    self.context.workspace,
                    self.context.tracer.directory / "final.patch",
                )
                self.state.final_patch_path = str(path)
            except Exception as exc:
                artifact_errors.append(f"patch:{type(exc).__name__}")
                self.state.status = "failed"
                self.state.stop_reason = self.state.stop_reason or "patch_export_failed"
            result = {
                "state": self.state.model_dump(),
                "artifact_errors": artifact_errors,
                "verification_scope": "Current public tests only; independent Eval pending",
            }
            try:
                self.persist()
                self.context.tracer.save_json("result.json", result)
            except Exception as exc:
                artifact_errors.append(f"trace:{type(exc).__name__}")
                self.state.status = "failed"
                self.state.stop_reason = "artifact_write_failed"
                result["state"] = self.state.model_dump()
        return result
