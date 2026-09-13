import json
from pathlib import Path

from config import Settings
from scripts.demo import run_demo


async def test_full_calculator_chain(tmp_path):
    result = await run_demo(
        Settings(
            _env_file=None,
            cache_dir=tmp_path / "cache",
            worktree_dir=tmp_path / "worktrees",
            runs_dir=tmp_path / "runs",
        )
    )
    assert result["status"] == "completed"
    assert result["baseline"]["exit_code"] == 1
    assert result["repaired"]["exit_code"] == 0
    assert result["verification"]["exit_code"] == 0
    assert result["retained_workspaces"] == []
    assert result["cleanup_errors"] == []
    patch = Path(result["patch_path"]).read_text()
    assert "int, float" in patch
    events = [json.loads(line) for line in Path(result["trace_path"]).read_text().splitlines()]
    assert len([event for event in events if event["event"] == "tool_finished"]) == 8
