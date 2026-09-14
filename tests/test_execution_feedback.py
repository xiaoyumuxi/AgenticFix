import asyncio
import json

import pytest

from agent.loop import AgentLoop
from sandbox.docker import DockerSandbox
from tools.base import ToolResult
from tools.factory import build_registry


@pytest.mark.parametrize(
    "name,success,exit_code",
    [
        ("build_environment", False, 1),
        ("run_tests", True, 2),
    ],
)
def test_long_execution_failure_keeps_status_and_error_tail(context, name, success, exit_code):
    result = ToolResult(
        success=success,
        error_code="ENVIRONMENT_BUILD_FAILED" if not success else None,
        data={
            "stdout": "setup started\n" + "progress\n" * 10000,
            "stderr": "first warning\n" + "download\n" * 3000 + "ERROR: missing-dependency\n",
            "exit_code": exit_code,
            "timed_out": False,
            "artifact": "environment-1.json",
        },
    )
    original = result.model_dump()
    loop = AgentLoop(None, build_registry(context))
    message = json.loads(loop.tool_message(result, name))
    assert message["success"] == success
    assert message["data"]["exit_code"] == exit_code
    assert message["data"]["timed_out"] is False
    assert "setup started" in message["data"]["stdout"]
    assert "first warning" in message["data"]["stderr"]
    assert "ERROR: missing-dependency" in message["data"]["stderr"]
    assert message["truncated"]
    assert result.model_dump() == original
    assert len(message["data"]["stderr"]) <= context.settings.max_tool_message_chars // 2


async def test_docker_capture_keeps_error_after_large_output(tmp_path, monkeypatch):
    class Process:
        returncode = 1
        stdout = asyncio.StreamReader()
        stderr = asyncio.StreamReader()

        async def wait(self):
            return 1

    process = Process()
    process.stdout.feed_data(b"start\n" + b"x" * 150000 + b"final stdout\n")
    process.stderr.feed_data(
        b"first warning\n"
        + b"y" * 80000
        + b"\nModuleNotFoundError: middle-error\n"
        + b"y" * 90000
        + b"ERROR: package unavailable\n"
    )
    process.stdout.feed_eof()
    process.stderr.feed_eof()

    async def create(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    sandbox = DockerSandbox(tmp_path, max_output_bytes=512)
    result = await sandbox.cli("version")
    assert result.exit_code == 1 and result.truncated
    assert len(result.stdout.encode()) <= 512
    assert len(result.stderr.encode()) <= 512
    assert result.stdout.startswith("start\n") and result.stdout.endswith("final stdout\n")
    assert result.stderr.startswith("first warning\n")
    assert result.stderr.endswith("ERROR: package unavailable\n")
    saved = json.loads((tmp_path / "cli-1.json").read_text())
    assert saved["result"]["stderr"] == result.stderr
    assert "middle-error" not in result.stderr
    assert any("middle-error" in line for line in result.diagnostic_lines)
    from agent.feedback import execution_failure_message

    message = execution_failure_message(ToolResult(success=False, data=result.model_dump()), 12000)
    assert "middle-error" in message
