"""Scripted tool integration demonstration. No model calls or hidden evaluation."""

import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.state import AgentState
from config import Settings
from tools.base import ToolResult
from tools.context import ToolContext
from tools.factory import build_registry
from tools.registry import ToolRegistry
from tracing.tracer import Tracer
from workspace.repository import Repository, Workspace, WorkspaceManager, git


async def require(registry: ToolRegistry, name: str, arguments: dict[str, Any]) -> ToolResult:
    result = await registry.call(name, arguments)
    if not result.success:
        raise RuntimeError(f"{name}: {result.error_code}: {result.error}")
    return result


def make_context(
    workspace: Workspace,
    manager: WorkspaceManager,
    settings: Settings,
    task_id: str,
) -> ToolContext:
    state = AgentState(
        task_id=task_id,
        run_id=workspace.run_id,
        base_commit=workspace.base_commit,
        workspace_path=str(workspace.path),
        issue="Support int and float addition",
    )
    return ToolContext(
        workspace=workspace,
        manager=manager,
        settings=settings,
        state=state,
        tracer=Tracer(settings.runs_dir / workspace.run_id),
        test_targets={"default": (sys.executable, "-m", "pytest", "-q")},
        trusted_local=True,
    )


async def run_demo(settings: Settings, *, keep_worktrees: bool = False) -> dict[str, Any]:
    run_id = f"calculator-{uuid4().hex[:12]}"
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = (settings.runs_dir / run_id).resolve()
    artifact_dir.mkdir()
    source = artifact_dir / "fixture-source"
    fixture = Path(__file__).resolve().parents[1] / "examples" / "calculator"
    source.mkdir()
    for name in ("calculator.py", "test_calculator.py", "issue.md", "pytest.ini"):
        shutil.copyfile(fixture / name, source / name)
    (source / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "AgenticFix Fixture")
    git(source, "config", "user.email", "fixture@agenticfix.invalid")
    git(source, "add", ".")
    git(source, "commit", "-m", "Initialize deliberately failing calculator")
    manager = WorkspaceManager(settings.cache_dir, settings.worktree_dir)
    repo = manager.prepare_repository(str(source))
    created: list[Workspace] = []
    contexts: list[ToolContext] = []
    completed = False
    summary: dict[str, Any] = {"run_id": run_id, "kind": "scripted_tool_demo"}
    try:
        workspace = manager.create_workspace(repo, run_id)
        created.append(workspace)
        context = make_context(workspace, manager, settings, "calculator")
        contexts.append(context)
        registry = build_registry(context)
        await require(registry, "list_files", {})
        await require(registry, "search_code", {"query": "def add", "file_pattern": "*.py"})
        read = await require(registry, "read_file", {"path": "calculator.py"})
        await require(registry, "read_file", {"path": "test_calculator.py"})
        baseline = await require(registry, "run_tests", {})
        if baseline.data["status"] != "failed":
            raise RuntimeError("Expected the deliberate issue to fail before editing")
        await require(
            registry,
            "edit_file",
            {
                "path": "calculator.py",
                "old_text": "if not isinstance(a, int) or not isinstance(b, int):",
                "new_text": (
                    "if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):"
                ),
                "version": read.data["version"],
            },
        )
        repaired = await require(registry, "run_tests", {})
        if not context.state.current_tests_passed:
            raise RuntimeError("Repaired fixture did not pass current-version tests")
        patch_result = await require(registry, "git_diff", {})
        patch = Path(patch_result.data["patch_path"])
        if not patch.read_bytes():
            raise RuntimeError("Expected a nonempty patch")
        verification = manager.create_workspace(
            Repository(repo.cache_path, repo.base_commit),
            f"{run_id}-verify",
        )
        created.append(verification)
        git(verification.path, "apply", "--check", str(patch))
        git(verification.path, "apply", "--binary", str(patch))
        verifier = make_context(verification, manager, settings, "calculator-verification")
        contexts.append(verifier)
        checked = await require(build_registry(verifier), "run_tests", {})
        if not verifier.state.current_tests_passed:
            raise RuntimeError("Patch failed tests in clean verification workspace")
        completed = True
        summary.update(
            {
                "status": "completed",
                "base_commit": repo.base_commit,
                "baseline": baseline.data,
                "repaired": repaired.data,
                "verification": checked.data,
                "patch_path": str(patch),
                "trace_path": str(context.tracer.path),
                "scope": "Public fixture tests only; not independent hidden evaluation",
            }
        )
    except Exception as exc:
        summary.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        # Preserve the best available patch without masking the original failure.
        if created:
            try:
                path = manager.export_patch(created[0], artifact_dir / "final.patch")
                summary["patch_path"] = str(path)
            except Exception as patch_error:
                summary["patch_error"] = type(patch_error).__name__
        raise
    finally:
        cleanup_errors: list[str] = []
        for workspace in created:
            try:
                manager.cleanup_workspace(workspace, retain=keep_worktrees or not completed)
            except Exception as exc:
                cleanup_errors.append(f"{workspace.run_id}: {type(exc).__name__}: {exc}")
        summary["retained_workspaces"] = [str(w.path) for w in created if w.path.exists()]
        summary["cleanup_errors"] = cleanup_errors
        for context in contexts:
            context.state.status = "completed" if completed else "failed"
            context.state.stop_reason = "demo_verified" if completed else "demo_failure"
            context.tracer.save_json("state.json", context.state.model_dump())
        Tracer(artifact_dir).save_json("result.json", summary)
    return summary
