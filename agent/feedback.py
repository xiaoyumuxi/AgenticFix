"""Bounded execution feedback preserving process status and both ends of logs."""

import json

from tools.base import ToolResult


def head_tail(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    marker = "\n...[middle omitted]...\n"
    room = max(0, limit - len(marker))
    head = room // 4
    tail = room - head
    return text[:head] + marker + (text[-tail:] if tail else "")


def execution_failure_message(result: ToolResult, limit: int) -> str:
    data = {
        key: value
        for key, value in result.data.items()
        if key
        in {
            "exit_code",
            "timed_out",
            "launch_error",
            "status",
            "target",
            "tested_revision",
            "image_id",
            "dockerfile_sha256",
            "duration",
            "total_duration",
            "cleanup_exit_code",
            "artifact",
        }
    }
    candidates = "\n".join(result.data.get("diagnostic_lines", []))
    data["diagnostic_excerpt"] = head_tail(candidates, limit // 4)
    # Each stream gets a share so a noisy stdout cannot hide stderr, or vice versa.
    for stream in ("stdout", "stderr"):
        data[stream] = head_tail(str(result.data.get(stream, "")), (limit * 3) // 8)
    return json.dumps(
        result.model_dump()
        | {
            "data": data,
            "truncated": True,
            "hint": "Execution log excerpts retain the beginning and end; the middle is omitted. "
            "Diagnostic excerpts are keyword-matched log lines, not a root-cause judgment. "
            "Use the exit status and actual error to revise the environment or source. "
            "The captured log is retained in the run artifact; it may itself be truncated.",
        },
        ensure_ascii=False,
    )
