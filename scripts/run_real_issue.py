"""A real issue, model-built environment, then independent fixed tests in Docker."""

import asyncio
import hashlib
import json
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.runner import run_agent
from config import Settings
from sandbox.docker import DockerSandbox
from tracing.tracer import Tracer
from workspace.repository import WorkspaceManager, git

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "eval/tasks/more-itertools-1152"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def verify(sandbox: DockerSandbox, source: Path) -> dict[str, Any]:
    run = await sandbox.run(
        (
            "python",
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "--junitxml=/results/report.xml",
            "tests",
            "test_issue_acceptance.py",
        ),
        source,
        120,
    )
    report = Path(sandbox.last_run["output_directory"]) / "report.xml"
    cases = {}
    if report.exists():
        for node in ET.parse(report).iter("testcase"):
            cases[f"{node.get('classname')}::{node.get('name')}"] = (
                "failed"
                if node.find("failure") is not None
                else "error"
                if node.find("error") is not None
                else "skipped"
                if node.find("skipped") is not None
                else "passed"
            )
    return run.model_dump() | {"cases": cases, "report": str(report)}


async def run() -> dict[str, Any]:
    started = time.monotonic()
    definition = json.loads((TASK / "task.json").read_text())
    issue = json.loads((TASK / "issue.json").read_text())
    settings = Settings(
        max_run_duration=900, max_test_timeout=120, max_build_timeout=300, max_token_budget=150000
    )
    directory = (settings.runs_dir / f"real-1152-{uuid4().hex[:12]}").resolve()
    tracer = Tracer(directory)
    result: dict[str, Any] = {"task": definition, "stage": "preparing", "solved": False}
    task_snapshot = definition | {
        "agent_commit": git(ROOT, "rev-parse", "HEAD").decode().strip(),
        "agent_dirty": bool(git(ROOT, "status", "--porcelain")),
        "issue_sha256": sha(TASK / "issue.json"),
        "acceptance_sha256": sha(TASK / "test_acceptance.py"),
        "prompt_version": settings.environment_prompt_version,
    }
    if task_snapshot["agent_dirty"]:
        raise RuntimeError("Commit implementation and frozen tests before a measured run")
    tracer.save_json("task-definition.json", task_snapshot)
    source = ROOT / ".cache/m3-upstream"
    try:
        result["stage"] = "agent_environment_and_repair"
        result["agent"] = await run_agent(
            settings,
            source=source,
            ref=definition["base_commit"],
            issue=issue["title"] + "\n\n" + issue["body"],
            docker=True,
            keep_worktrees=True,
        )
        tracer.save_json("summary.json", result)
        agent_dir = Path(result["agent"]["run_directory"])
        patch = Path(result["agent"]["state"]["final_patch_path"])
        result["patch_sha256"] = sha(patch)
        shutil.copyfile(patch, directory / "candidate.patch")
        dockerfiles = sorted(
            (agent_dir / "environment").glob("build-*.Dockerfile"),
            key=lambda p: int(p.stem.split("-")[1]),
        )
        if not dockerfiles or not result["agent"].get("environment", {}).get("image_id"):
            result["stage"] = "environment_failed"
            return result
        shutil.copyfile(dockerfiles[-1], directory / "Dockerfile")
        manager = WorkspaceManager(settings.cache_dir, settings.worktree_dir)
        repo = manager.prepare_repository(str(source), definition["base_commit"])
        work = manager.create_workspace(repo, "eval-" + uuid4().hex[:12])
        sandbox = DockerSandbox(directory / "verification-environment")
        try:
            result["stage"] = "clean_environment_rebuild"
            rebuilt = await sandbox.build((directory / "Dockerfile").read_text(), work.path, 300)
            result["rebuild"] = rebuilt.model_dump() | sandbox.last_build
            if rebuilt.exit_code != 0 or rebuilt.timed_out:
                return result
            provenance = await sandbox.run(
                (
                    "python",
                    "-c",
                    "import more_itertools,sys; print(sys.version); "
                    "print(more_itertools.__file__); "
                    "assert more_itertools.__file__.startswith('/workspace/')",
                ),
                work.path,
                30,
            )
            freeze = await sandbox.run(("python", "-m", "pip", "freeze", "--all"), work.path, 30)
            result["provenance"] = provenance.model_dump()
            result["dependencies"] = freeze.model_dump()
            if provenance.exit_code != 0:
                return result
            acceptance = TASK / "test_acceptance.py"
            shutil.copyfile(acceptance, work.path / "test_issue_acceptance.py")
            result["stage"] = "independent_verification"
            result["before"] = await verify(sandbox, work.path)
            tracer.save_json("summary.json", result)
            # Only evaluator reads the official source diff. Agent context never receives it.
            official = git(
                source,
                "diff",
                definition["base_commit"],
                definition["official_fix_commit"],
                "--",
                "more_itertools/more.py",
            )
            (directory / "official-source.patch").write_bytes(official)
            git(work.path, "apply", str(directory / "official-source.patch"))
            result["official"] = await verify(sandbox, work.path)
            git(
                work.path,
                "restore",
                "--source",
                definition["base_commit"],
                "--",
                "more_itertools/more.py",
            )
            if patch.stat().st_size:
                git(work.path, "apply", "--check", str(patch))
                git(work.path, "apply", str(patch))
            # Freeze original regression tests/config, then restore independent tests.
            git(
                work.path,
                "restore",
                "--source",
                definition["base_commit"],
                "--",
                "tests",
                "setup.cfg",
                "pyproject.toml",
                "tox.ini",
            )
            shutil.copyfile(acceptance, work.path / "test_issue_acceptance.py")
            result["after"] = await verify(sandbox, work.path)
            before = result["before"]["cases"]
            after = result["after"]["cases"]
            failures = [k for k, v in before.items() if v == "failed"]
            result["new_regressions"] = [
                k for k, v in before.items() if v == "passed" and after.get(k) != "passed"
            ]
            result["missing_cases"] = sorted(set(before) - set(after))
            result["task_valid"] = (
                bool(failures)
                and all(k.startswith("test_issue_acceptance::") for k in failures)
                and result["before"]["exit_code"] == 1
                and result["official"]["exit_code"] == 0
                and set(before) == set(result["official"]["cases"])
            )
            result["issue_fixed"] = all(after.get(k) == "passed" for k in failures)
            result["solved"] = (
                result["task_valid"]
                and result["issue_fixed"]
                and result["agent"]["state"]["status"] == "completed"
                and bool(patch.stat().st_size)
                and result["after"]["exit_code"] == 0
                and not result["new_regressions"]
                and not result["missing_cases"]
            )
            result["stage"] = "completed" if result["solved"] else "verification_failed"
        finally:
            manager.cleanup_workspace(work, retain=not result["solved"])
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        raise
    finally:
        result["total_duration"] = time.monotonic() - started
        tracer.save_json("summary.json", result)
    return result


if __name__ == "__main__":
    result = asyncio.run(run())
    # No assistant prose or private model reasoning in console output.
    print(
        json.dumps({k: v for k, v in result.items() if k != "agent"}, ensure_ascii=False, indent=2)
    )
    raise SystemExit(0 if result["solved"] else 1)
