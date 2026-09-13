"""Versioned local evidence. Public archives still require review before publication."""

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.prompts import SYSTEM_PROMPT
from config import Settings
from tracing.tracer import Tracer
from workspace.repository import WorkspaceError, git


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture_start(tracer: Tracer, settings: Settings, root: Path) -> None:
    version: dict[str, Any] = {"commit": None, "dirty": None}
    try:
        version["commit"] = git(root, "rev-parse", "HEAD").decode().strip()
        status = git(root, "status", "--porcelain=v1", "-z")
        version["dirty"] = bool(status)
        diff = git(root, "diff", "--binary", "HEAD", "--")
        untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
        version["untracked_sha256"] = {
            name: digest((root / name).read_bytes())
            for name in untracked.decode().split("\0")
            if name and (root / name).is_file() and not (root / name).is_symlink()
        }
        version["untracked_contents_archived"] = False
        version["tracked_diff_sha256"] = digest(diff)
        # Diff can contain secrets: save only a redacted local copy, retaining both hashes.
        safe_diff = tracer.redact(diff.decode("utf-8", errors="replace"))
        tracer.save_json("agent-diff.json", {"patch": safe_diff})
        version["redacted_diff_sha256"] = digest(safe_diff.encode())
    except (WorkspaceError, OSError) as exc:
        version["capture_error"] = type(exc).__name__
    model = settings.llm_config()
    config = settings.model_dump(
        mode="json",
        exclude={"model_api_key", "model_extra_headers", "model_extra_body", "model_base_url"},
    )
    config["resolved_model"] = model.public_info() | {
        "timeout": model.timeout,
        "extra_body": model.extra_body,
        "extra_header_names": sorted(model.extra_headers),
    }
    packages = {}
    for name in ("agentic-fix", "httpx", "pydantic", "pytest", "pydantic-settings"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    lock = root / "uv.lock"
    tracer.save_json(
        "metadata.json",
        {
            "schema_version": 1,
            "captured_at": datetime.now(UTC).isoformat(),
            "local_timezone": str(datetime.now().astimezone().tzinfo),
            "agent": version,
            "config": config,
            "environment": {
                "python": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "packages": packages,
            },
            "lock_sha256": digest(lock.read_bytes()) if lock.exists() else None,
            "system_prompt": SYSTEM_PROMPT,
            "system_prompt_sha256": digest(SYSTEM_PROMPT.encode()),
        },
    )


def finalize_evidence(tracer: Tracer) -> None:
    """Summarize measurements without exporting assistant prose or reasoning."""
    requests = []
    tests = []
    tools = []
    if tracer.path.exists():
        for line in tracer.path.read_text().splitlines():
            event = json.loads(line)
            kind = event["event"]
            if kind in {"model_finished", "model_failed"}:
                response = (event.get("result") or {}).get("response", {})
                requests.append(
                    {
                        "event": kind,
                        "call_id": event.get("call_id"),
                        "duration": event.get("duration"),
                        "usage": response.get("usage"),
                        "model": response.get("model"),
                        "error_code": (event.get("result") or {}).get("error_code"),
                    }
                )
            if kind in {"tool_finished", "tool_rejected"}:
                result = event.get("result") or {}
                tools.append(
                    {
                        "tool": event.get("tool"),
                        "duration": event.get("duration"),
                        "success": result.get("success"),
                        "error_code": result.get("error_code"),
                    }
                )
                if event.get("tool") == "run_tests":
                    tests.append(result.get("data", {}))
    tracer.save_json("measurements.json", {"requests": requests, "tools": tools, "tests": tests})
    artifacts = {
        path.name: {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
        for path in sorted(tracer.directory.iterdir())
        if path.is_file()
        and not path.name.startswith(".")
        and path.name != "manifest.json"
        and not path.is_symlink()
    }
    tracer.save_json(
        "manifest.json",
        {
            "schema_version": 1,
            "finished_at": datetime.now(UTC).isoformat(),
            "scope": "Top-level artifacts, excluding manifest. Local; publication needs review.",
            "artifacts": artifacts,
        },
    )
