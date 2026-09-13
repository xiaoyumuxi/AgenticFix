import json

import pytest
from pydantic import ValidationError

from agent.state import AgentState
from config import Settings
from tools.file_tools import ReadFile
from tracing.models import TraceEvent
from tracing.tracer import Tracer


def test_config_validation_and_env(monkeypatch):
    monkeypatch.setenv("AGENTICFIX_MAX_READ_LINES", "17")
    assert Settings(_env_file=None).max_read_lines == 17
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_file_bytes=0)


def test_state_has_independent_lists_and_invalidates_tests():
    a = AgentState(task_id="a", run_id="a", base_commit="x", workspace_path="/a")
    b = a.model_copy(deep=True)
    a.test_status = "passed"
    a.tested_revision = 0
    assert a.current_tests_passed
    a.record_edit("a.py")
    assert not a.current_tests_passed
    assert b.modified_files == []


def test_trace_persists_and_redacts(tmp_path):
    tracer = Tracer(tmp_path, secrets=("private-value",))
    tracer.append(
        TraceEvent(
            run_id="a",
            event="start",
            tool="read",
            call_id="1",
            arguments={"api_key": "x", "text": "private-value"},
        )
    )
    text = tracer.path.read_text()
    assert "private-value" not in text
    event = json.loads(text)
    assert event["arguments"]["api_key"] == "[REDACTED]"
    assert len(Tracer(tmp_path).path.read_text().splitlines()) == 1


async def test_registry_validation_and_trace(registry, context):
    with pytest.raises(ValueError):
        registry.register(ReadFile())
    assert len(registry.schemas()) == 6
    assert (await registry.call("missing", {})).error_code == "UNKNOWN_TOOL"
    assert (
        await registry.call("read_file", {"path": "sample.py", "extra": 1})
    ).error_code == "INVALID_ARGUMENTS"
    assert (await registry.call("read_file", {"path": "absent"})).error_code == "NOT_FOUND"
    assert (await registry.call("read_file", {"path": "sample.py"})).success
    events = [json.loads(line) for line in context.tracer.path.read_text().splitlines()]
    assert len(events) == 8
    assert all(events[i]["call_id"] == events[i + 1]["call_id"] for i in range(0, 8, 2))
    assert context.state.total_tool_calls == 4


async def test_unexpected_error_stops_run(registry, context, monkeypatch):
    async def broken(*args):
        raise RuntimeError("internal invariant")

    monkeypatch.setattr(registry.tools["read_file"], "execute", broken)
    result = await registry.call("read_file", {"path": "sample.py"})
    assert result.fatal and result.error_code == "INTERNAL_ERROR"
    assert context.state.status == "failed"
    assert (await registry.call("list_files", {})).error_code == "RUN_STOPPED"
    assert "INTERNAL_ERROR" in context.tracer.path.read_text()


async def test_trace_failure_prevents_edit(registry, context, monkeypatch):
    def fail(event):
        raise OSError("disk full")

    monkeypatch.setattr(context.tracer, "append", fail)
    result = await registry.call(
        "edit_file",
        {
            "path": "sample.py",
            "old_text": "value = 1",
            "new_text": "value = 2",
            "version": "0" * 64,
        },
    )
    assert result.fatal and result.error_code == "TRACE_FAILURE"
    assert "value = 1" in (context.workspace.path / "sample.py").read_text()


async def test_recoverable_io_error(registry, context, monkeypatch):
    original = context.read

    def fail(path):
        raise PermissionError("denied")

    monkeypatch.setattr(context, "read", fail)
    result = await registry.call("read_file", {"path": "sample.py"})
    assert result.error_code == "IO_ERROR" and not result.fatal
    monkeypatch.setattr(context, "read", original)
    assert (await registry.call("read_file", {"path": "sample.py"})).success
