import asyncio
import json
from collections import deque
from pathlib import Path

import pytest

from agent.llm import AssistantMessage, LLMClient, ModelError, ModelReply, Usage
from agent.loop import AgentLoop
from tools.factory import build_registry
from workspace.repository import Repository, git


def reply_call(name, args, call_id="call", *, usage=True):
    return ModelReply(
        message=AssistantMessage.model_validate(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            }
        ),
        finish_reason="tool_calls",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15) if usage else None,
    )


def reply_final(text="Candidate patch is ready.", *, finish="stop"):
    return ModelReply(
        message=AssistantMessage(role="assistant", content=text),
        finish_reason=finish,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


class QueueClient(LLMClient):
    def __init__(self, replies):
        self.replies = deque(replies)
        self.requests = []

    async def generate(self, messages, tools, max_tokens):
        self.requests.append(json.loads(json.dumps(messages)))
        item = self.replies.popleft()
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(messages)
        return item


def last_tool_data(messages):
    return json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))["data"]


def edit_after_read(old, new):
    return lambda messages: reply_call(
        "edit_file",
        {
            "path": "sample.py",
            "old_text": old,
            "new_text": new,
            "version": last_tool_data(messages)["version"],
        },
    )


@pytest.mark.parametrize(
    "body,expected",
    [
        ("def calculate(a, b):\n    return a - b\n", "assert calculate(2, 3) == 5"),
        ("def calculate(a, b):\n    return a * b\n", "assert calculate(2, 3) == 5"),
        ("def calculate(a, b):\n    return a / b\n", "assert calculate(2, 3) == 5"),
    ],
)
async def test_three_offline_tasks_repair_and_clean_apply(context, body, expected):
    # Deterministic clients exercise orchestration, not real-model success rate.
    (context.workspace.path / "sample.py").write_text(body)
    (context.workspace.path / "test_sample.py").write_text(
        "from sample import calculate\ndef test_issue():\n    " + expected + "\n",
    )
    context.state.issue = "Correct calculate to add two numbers."
    client = QueueClient(
        [
            reply_call("read_file", {"path": "test_sample.py"}),
            reply_call("read_file", {"path": "sample.py"}),
            edit_after_read(body, "def calculate(a, b):\n    return a + b\n"),
            reply_call("run_tests", {}),
            reply_final(),
        ]
    )
    result = await AgentLoop(client, build_registry(context)).run()
    assert result["state"]["status"] == "completed"
    assert result["state"]["reported_tokens"] == 75
    assert result["state"]["unknown_usage_requests"] == 0
    patch = Path(result["state"]["final_patch_path"])
    verify = context.manager.create_workspace(
        Repository(context.workspace.cache_path, context.workspace.base_commit),
        "clean-verify",
    )
    git(verify.path, "apply", "--check", str(patch))
    git(verify.path, "apply", str(patch))
    assert "return a + b" in (verify.path / "sample.py").read_text()
    assert (context.tracer.directory / "messages.json").exists()


async def test_failed_edit_test_feedback_retry(context):
    path = context.workspace.path / "sample.py"
    path.write_text("value = 1\n")
    (context.workspace.path / "test_sample.py").write_text(
        "from sample import value\ndef test_value():\n    assert value == 3\n",
    )
    client = QueueClient(
        [
            reply_call("read_file", {"path": "sample.py"}),
            edit_after_read("value = 1", "value = 2"),
            reply_call("run_tests", {}),
            reply_final("Premature finish"),
            reply_call("read_file", {"path": "sample.py"}),
            edit_after_read("value = 2", "value = 3"),
            reply_final(),
        ]
    )
    result = await AgentLoop(client, build_registry(context)).run()
    assert result["state"]["status"] == "completed"
    assert result["state"]["workspace_revision"] == 2
    assert any("Completion rejected" in str(m) for r in client.requests for m in r)
    assert "failed" in str(client.requests[3])


@pytest.mark.parametrize(
    "setting,value,reason",
    [
        ("max_iterations", 1, "iteration_budget"),
        ("max_tool_calls", 1, "tool_budget"),
        ("max_token_budget", 1, "token_budget"),
        ("max_context_bytes", 100, "context_budget"),
    ],
)
async def test_budget_stops_preserve_artifacts(context, setting, value, reason):
    setattr(context.settings, setting, value)
    client = QueueClient([reply_call("read_file", {"path": "sample.py"})] * 10)
    result = await AgentLoop(client, build_registry(context)).run()
    assert result["state"]["stop_reason"] == reason
    assert Path(result["state"]["final_patch_path"]).is_file()
    assert result["state"]["total_tool_calls"] <= context.settings.max_tool_calls


async def test_multi_tool_batch_cannot_bypass_budget(context):
    context.settings.max_tool_calls = 2  # baseline + one model tool
    reply = reply_call("read_file", {"path": "sample.py"})
    second = reply.message.tool_calls[0].model_copy(deep=True)
    second.id = "second"
    reply.message.tool_calls.append(second)
    result = await AgentLoop(QueueClient([reply]), build_registry(context)).run()
    assert result["state"]["stop_reason"] == "tool_budget"
    assert result["state"]["total_tool_calls"] == 2


async def test_model_retry_usage_and_auth_failure(context):
    context.settings.retry_delay = 0
    client = QueueClient(
        [
            ModelError("HTTP_429", retryable=True),
            reply_call("read_file", {"path": "sample.py"}, usage=False),
            ModelError("HTTP_401"),
        ]
    )
    result = await AgentLoop(client, build_registry(context)).run()
    assert result["state"]["stop_reason"] == "HTTP_401"
    assert result["state"]["unknown_usage_requests"] == 3
    assert result["state"]["estimated_tokens"] > 0
    assert len(client.requests) == 3


async def test_invalid_arguments_feedback_and_repetition(context):
    malformed = reply_call("read_file", {})
    malformed.message.tool_calls[0].function.arguments = "not JSON"
    client = QueueClient([malformed] + [reply_call("read_file", {"path": "missing"})] * 5)
    result = await AgentLoop(client, build_registry(context)).run()
    assert result["state"]["stop_reason"] == "repeated_action"
    assert "INVALID_JSON" in str(client.requests[1])
    assert "NOT_FOUND" in str(client.requests[2])


async def test_truncated_completion_never_executes_tools(context):
    reply = reply_call("read_file", {"path": "sample.py"})
    reply.finish_reason = "length"
    result = await AgentLoop(QueueClient([reply]), build_registry(context)).run()
    assert result["state"]["stop_reason"] == "model_finish_length"
    assert result["state"]["total_tool_calls"] == 1  # only baseline


async def test_run_timeout_accounts_for_inflight_model_and_exports(context):
    class Slow(LLMClient):
        async def generate(self, messages, tools, max_tokens):
            await asyncio.sleep(10)

    context.settings.max_run_duration = 2
    result = await AgentLoop(Slow(), build_registry(context)).run()
    assert result["state"]["stop_reason"] == "run_timeout"
    assert result["state"]["estimated_tokens"] > 0
    assert Path(result["state"]["final_patch_path"]).exists()


async def test_empty_patch_is_not_success(context):
    context.settings.max_iterations = 2
    result = await AgentLoop(QueueClient([reply_final()] * 2), build_registry(context)).run()
    assert result["state"]["status"] == "failed"
    assert "empty patch" in (context.tracer.directory / "messages.json").read_text()


async def test_tools_return_bounded_model_context(context):
    context.settings.max_tool_message_chars = 200
    loop = AgentLoop(QueueClient([]), build_registry(context))
    from tools.base import ToolResult

    clipped = json.loads(loop.tool_message(ToolResult(success=True, data={"output": "x" * 10000})))
    assert clipped["truncated"]
    assert len(clipped["preview"]) == 200
