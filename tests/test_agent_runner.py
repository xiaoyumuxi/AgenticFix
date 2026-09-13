import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from agent.llm import OpenAICompatibleClient
from agent.runner import run_agent
from config import Settings


async def test_http_adapter_to_runner_full_chain(tmp_path, monkeypatch):
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        step = len(requests)
        if step <= 2:
            name = "read_file"
            args = {"path": "test_calculator.py" if step == 1 else "calculator.py"}
        elif step == 3:
            read = json.loads(payload["messages"][-1]["content"])
            name = "edit_file"
            args = {
                "path": "calculator.py",
                "version": read["data"]["version"],
                "old_text": "if not isinstance(a, int) or not isinstance(b, int):",
                "new_text": (
                    "if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):"
                ),
            }
        else:
            # A mock final exercises real runtime verification, not a real-model claim.
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "Ready",
                                "reasoning_content": "opaque-state",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            )
        message = {
            "role": "assistant",
            "content": None,
            "reasoning_content": "opaque-state",
            "tool_calls": [
                {
                    "id": f"call-{step}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args),
                    },
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "tool_calls", "message": message}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    monkeypatch.setattr(
        "agent.runner.OpenAICompatibleClient",
        lambda config: OpenAICompatibleClient(config, transport=httpx.MockTransport(handler)),
    )
    settings = Settings(
        _env_file=None,
        cache_dir=tmp_path / "cache",
        worktree_dir=tmp_path / "worktrees",
        runs_dir=tmp_path / "runs",
        model_api_key=SecretStr("never-log-this-key"),
    )
    result = await run_agent(settings)
    assert result["state"]["status"] == "completed"
    assert result["state"]["model_requests"] == 4
    assert result["retained_workspace"] is None
    assert "int, float" in Path(result["state"]["final_patch_path"]).read_text()
    for path in Path(result["run_directory"]).glob("*.json*"):
        assert "never-log-this-key" not in path.read_text()
    previous_assistants = [m for m in requests[-1]["messages"] if m["role"] == "assistant"]
    assert len(previous_assistants) == 3
    assert all(m["reasoning_content"] == "opaque-state" for m in previous_assistants)
    assert requests[0]["model"] == "deepseek-flash"


async def test_missing_key_and_untrusted_repo_fail_before_worktree(tmp_path):
    settings = Settings(
        _env_file=None,
        cache_dir=tmp_path / "cache",
        worktree_dir=tmp_path / "worktrees",
        runs_dir=tmp_path / "runs",
    )
    with pytest.raises(ValueError, match="AGENTICFIX_MODEL_API_KEY"):
        await run_agent(settings)
    assert not settings.worktree_dir.exists()
    settings.model_api_key = SecretStr("test")
    with pytest.raises(ValueError, match="trusted-local"):
        await run_agent(settings, source=tmp_path, issue="fix")
    assert not settings.worktree_dir.exists()


async def test_auth_failure_retains_scene_without_leaking_server_body(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent.runner.OpenAICompatibleClient",
        lambda config: OpenAICompatibleClient(
            config,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, text="provider-secret-error")
            ),
        ),
    )
    result = await run_agent(
        Settings(
            _env_file=None,
            cache_dir=tmp_path / "cache",
            worktree_dir=tmp_path / "worktrees",
            runs_dir=tmp_path / "runs",
            model_api_key=SecretStr("not-a-real-key"),
        )
    )
    assert result["state"]["stop_reason"] == "HTTP_401"
    assert Path(result["retained_workspace"]).is_dir()
    assert "provider-secret-error" not in json.dumps(result)
    assert Path(result["state"]["final_patch_path"]).is_file()
