"""CLI-facing run setup. External untrusted execution still requires the Docker milestone."""

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.llm import OpenAICompatibleClient
from agent.loop import AgentLoop
from agent.prompts import prompt_for_environment
from agent.state import AgentState
from config import Settings
from sandbox.docker import DockerSandbox
from tools.context import ToolContext
from tools.factory import build_registry
from tracing.evidence import capture_start, finalize_evidence
from tracing.tracer import Tracer
from workspace.repository import WorkspaceManager, git


async def run_agent(
    settings: Settings,
    *,
    source: Path | None = None,
    issue: str | None = None,
    ref: str = "HEAD",
    trusted_local: bool = False,
    keep_worktrees: bool = False,
    docker: bool = False,
) -> dict[str, Any]:
    model = settings.llm_config()
    model.require_key()  # Fail before creating workspaces or sending repository data.
    if source is not None and not trusted_local and not docker:
        raise ValueError("Custom local repositories require --trusted-local; Docker is not ready")
    if source is not None and (not source.is_dir() or not issue or not issue.strip()):
        raise ValueError("Provide an existing local repository and nonempty issue")
    run_id = f"agent-{uuid4().hex[:12]}"
    directory = (settings.runs_dir / run_id).resolve()
    tracer = Tracer(
        directory,
        secrets=(
            model.api_key.get_secret_value(),
            *(v.get_secret_value() for v in model.extra_headers.values()),
        ),
    )
    try:
        capture_start(
            tracer,
            settings,
            Path(__file__).resolve().parents[1],
            prompt_for_environment(settings.environment_prompt_version if docker else None),
        )
        tracer.save_json(
            "prompt.json",
            {
                "version": settings.environment_prompt_version if docker else "repair-v1",
                "text": prompt_for_environment(
                    settings.environment_prompt_version if docker else None
                ),
            },
        )
        return await _run_prepared(
            settings, tracer, run_id, source, issue, ref, keep_worktrees, docker
        )
    except (Exception, asyncio.CancelledError) as exc:
        tracer.save_json(
            "runner-error.json",
            {
                "run_id": run_id,
                "status": "failed",
                "error_type": type(exc).__name__,
                "message": "Runner aborted; inspect local artifacts. Raw exception omitted.",
            },
        )
        raise
    finally:
        finalize_evidence(tracer)


async def _run_prepared(
    settings: Settings,
    tracer: Tracer,
    run_id: str,
    source: Path | None,
    issue: str | None,
    ref: str,
    keep_worktrees: bool,
    docker: bool,
) -> dict[str, Any]:
    model = settings.llm_config()
    directory = tracer.directory
    tracer.save_json("model.json", model.public_info())
    if source is None:
        source = directory / "fixture-source"
        source.mkdir()
        fixture = Path(__file__).resolve().parents[1] / "examples" / "calculator"
        for name in ("calculator.py", "test_calculator.py", "pytest.ini", "issue.md"):
            shutil.copyfile(fixture / name, source / name)
        (source / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        issue = (source / "issue.md").read_text()
        # Only requirements go to the model, not the scripted demo explanation.
        issue = issue.split("This is an intentionally")[0].strip()
        git(source, "init", "-b", "main")
        git(source, "config", "user.name", "AgenticFix Fixture")
        git(source, "config", "user.email", "fixture@agenticfix.invalid")
        git(source, "add", ".")
        git(source, "commit", "-m", "Initialize agent fixture")
    manager = WorkspaceManager(settings.cache_dir, settings.worktree_dir)
    repo = manager.prepare_repository(str(source), ref)
    tracer.save_json(
        "task.json",
        {
            "run_id": run_id,
            "source": str(source.resolve()),
            "requested_ref": ref,
            "base_commit": repo.base_commit,
            "issue": issue,
            "test_command": ["python" if docker else sys.executable, "-m", "pytest", "-q"],
            "execution": "docker" if docker else "trusted-local",
        },
    )
    workspace = manager.create_workspace(repo, run_id)
    context = ToolContext(
        workspace=workspace,
        manager=manager,
        settings=settings,
        state=AgentState(
            task_id="local-issue",
            run_id=run_id,
            base_commit=repo.base_commit,
            workspace_path=str(workspace.path),
            issue=issue or "",
        ),
        tracer=tracer,
        trusted_local=not docker,
        docker=DockerSandbox(directory / "environment", max_output_bytes=settings.max_output_bytes)
        if docker
        else None,
        test_targets={"default": ("python" if docker else sys.executable, "-m", "pytest", "-q")},
    )
    if context.docker:
        probe = await context.docker.cli("version", "--format", "{{json .}}")
        tracer.save_json("docker-version.json", probe.model_dump())
        if probe.exit_code != 0:
            raise ValueError("Docker daemon unavailable; inspect docker-version.json")
    client = OpenAICompatibleClient(model)
    try:
        result = await AgentLoop(client, build_registry(context)).run()
    finally:
        await client.aclose()
    cleanup_errors: list[str] = []
    try:
        manager.cleanup_workspace(
            workspace, retain=(keep_worktrees or context.state.status != "completed")
        )
    except Exception as exc:
        cleanup_errors.append(type(exc).__name__)
    result.update(
        {
            "model": model.public_info(),
            "run_directory": str(directory),
            "retained_workspace": str(workspace.path) if workspace.path.exists() else None,
            "cleanup_errors": cleanup_errors,
            "environment": context.docker.last_build if context.docker else None,
        }
    )
    tracer.save_json("result.json", result)
    return result
