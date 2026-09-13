"""Frozen trusted tasks with held-out checks; not an external repository benchmark.

Run: uv run python -m scripts.validate_tasks order_total
"""

import argparse
import asyncio
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.runner import run_agent
from config import Settings
from sandbox.local import LocalSandbox
from tracing.evidence import digest
from tracing.tracer import Tracer
from workspace.repository import WorkspaceManager, git

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("order_total", "intervals")


async def verify(directory: Path, report: Path) -> dict[str, Any]:
    result = await LocalSandbox(trusted=True, max_output_bytes=1_048_576).run(
        (sys.executable, "-m", "pytest", "-q", f"--junitxml={report}"), directory, 60
    )
    cases = {}
    if report.exists():
        for case in ET.parse(report).iter("testcase"):
            name = f"{case.get('classname')}::{case.get('name')}"
            cases[name] = (
                "failed"
                if case.find("failure") is not None
                else "error"
                if case.find("error") is not None
                else "skipped"
                if case.find("skipped") is not None
                else "passed"
            )
    return result.model_dump() | {"cases": cases}


async def run_task(name: str) -> dict[str, Any]:
    settings = Settings()
    experiment = f"{name}-{uuid4().hex[:12]}"
    directory = (settings.runs_dir / experiment).resolve()
    tracer = Tracer(directory)
    fixture = ROOT / "examples" / name
    acceptance = ROOT / "validation" / name
    frozen = {
        str(p.relative_to(ROOT)): digest(p.read_bytes())
        for folder in (fixture, acceptance)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    }
    tracer.save_json(
        "task-definition.json",
        {
            "task": name,
            "agent_commit": git(ROOT, "rev-parse", "HEAD").decode().strip(),
            "frozen_files": frozen,
            "scope": "Trusted authored fixture; checks frozen before model run",
        },
    )
    source = directory / "source"
    shutil.copytree(fixture, source, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (source / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "AgenticFix Fixture")
    git(source, "config", "user.email", "fixture@agenticfix.invalid")
    git(source, "add", ".")
    git(
        source,
        "commit",
        "-m",
        f"Freeze {name}",
        env={
            "GIT_AUTHOR_DATE": "2026-09-14T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-09-14T00:00:00Z",
        },
    )
    manager = WorkspaceManager(settings.cache_dir, settings.worktree_dir)
    repo = manager.prepare_repository(str(source))
    workspace = manager.create_workspace(repo, f"verify-{experiment}")
    result: dict[str, Any] = {
        "task": name,
        "base_commit": repo.base_commit,
        "experiment_directory": str(directory),
    }
    try:
        shutil.copyfile(acceptance / "test_acceptance.py", workspace.path / "test_acceptance.py")
        result["before"] = await verify(workspace.path, directory / "before.xml")
        tracer.save_json("before.json", result["before"])
        if result["before"]["exit_code"] != 1 or not result["before"]["cases"]:
            raise RuntimeError("Baseline must contain reproducible assertion failures")
        result["run"] = await run_agent(
            settings, source=source, issue=(source / "issue.md").read_text(), trusted_local=True
        )
        patch = Path(result["run"]["state"]["final_patch_path"])
        shutil.copyfile(patch, directory / "final.patch")
        result["patch_sha256"] = digest(patch.read_bytes())
        if patch.stat().st_size:
            git(workspace.path, "apply", "--check", str(patch))
            git(workspace.path, "apply", str(patch))
        # Restore immutable acceptance inputs even if the agent changed public tests/config.
        for original in fixture.glob("test_*.py"):
            shutil.copyfile(original, workspace.path / original.name)
        shutil.copyfile(fixture / "pytest.ini", workspace.path / "pytest.ini")
        shutil.copyfile(acceptance / "test_acceptance.py", workspace.path / "test_acceptance.py")
        result["after"] = await verify(workspace.path, directory / "after.xml")
        before = result["before"]["cases"]
        after = result["after"]["cases"]
        result["new_regressions"] = [
            k for k, v in before.items() if v == "passed" and after.get(k) != "passed"
        ]
        result["missing_cases"] = sorted(set(before) - set(after))
        result["solved"] = (
            result["run"]["state"]["status"] == "completed"
            and bool(patch.stat().st_size)
            and result["after"]["exit_code"] == 0
            and not result["new_regressions"]
            and not result["missing_cases"]
        )
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["solved"] = False
        raise
    finally:
        tracer.save_json("summary.json", result)
        manager.cleanup_workspace(workspace, retain=not result.get("solved", False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=TASKS)
    result = asyncio.run(run_task(parser.parse_args().task))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["solved"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
