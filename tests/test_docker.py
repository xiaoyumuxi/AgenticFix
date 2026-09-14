import asyncio
import json
import os
from pathlib import Path

import pytest

from sandbox.base import ExecutionResult
from sandbox.docker import DockerSandbox, snapshot, validate_dockerfile


def test_snapshot_excludes_metadata_secrets_and_rejects_links(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / ".git").write_text("gitdir: /private/shared")
    (source / ".env").write_text("SECRET=private")
    (source / "hello.py").write_text("x=1")
    out = tmp_path / "out"
    snapshot(source, out)
    assert sorted(p.name for p in out.iterdir()) == ["hello.py"]
    (source / "escape").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="symlink"):
        snapshot(source, tmp_path / "rejected")


@pytest.mark.parametrize(
    "text",
    [
        "FROM ubuntu:latest",
        "FROM python:3.12-slim\nADD https://example.org/x /x",
        "FROM python:3.12-slim\nRUN --mount=type=secret,id=key cat /run/secrets/key",
        "# syntax=evil/frontend\nFROM python:3.12-slim",
        "FROM python:3.12-slim\nCOPY /etc /etc",
        "FROM python:3.12-slim\nFROM python:3.11-slim",
    ],
)
def test_reject_unsupported_build_input(text):
    with pytest.raises(ValueError):
        validate_dockerfile(text)


async def test_build_failure_drops_previous_image_and_cleans_builder(tmp_path, monkeypatch):
    sandbox = DockerSandbox(tmp_path / "artifacts")
    sandbox.image_id = "sha256:old"
    source = tmp_path / "repo"
    source.mkdir()
    calls = []

    async def cli(*args, **kwargs):
        calls.append(args)
        return ExecutionResult(duration=0, exit_code=7 if args[:2] == ("buildx", "build") else 0)

    monkeypatch.setattr(sandbox, "cli", cli)
    result = await sandbox.build("FROM python:3.12-slim\nRUN exit 7\n", source)
    assert result.exit_code == 7
    assert sandbox.image_id is None
    assert any(c[:2] == ("buildx", "rm") for c in calls)
    assert "memory=2g" in calls[0][-1]
    assert (await sandbox.run(("python", "-V"), source, 5)).launch_error == "ENVIRONMENT_NOT_READY"


async def test_cancelled_container_is_removed_and_mount_is_readonly(tmp_path, monkeypatch):
    sandbox = DockerSandbox(tmp_path / "artifacts")
    sandbox.image_id = "sha256:test"
    source = tmp_path / "repo"
    source.mkdir()
    calls = []

    async def cli(*args, **kwargs):
        calls.append(args)
        if args[0] == "run":
            assert "--network=none" in args and "--read-only" in args
            assert "--user=65534:65534" in args and "--pids-limit=128" in args
            mounts = [args[i + 1] for i, v in enumerate(args) if v == "--mount"]
            assert len(mounts) == 2 and mounts[0].endswith("dst=/workspace,readonly")
            raise asyncio.CancelledError
        return ExecutionResult(duration=0, exit_code=0)

    monkeypatch.setattr(sandbox, "cli", cli)
    with pytest.raises(asyncio.CancelledError):
        await sandbox.run(("python", "-V"), source, 5)
    assert calls[-1][:2] == ("rm", "-f")


@pytest.mark.skipif(
    os.environ.get("AGENTICFIX_DOCKER_TEST") != "1", reason="Explicit Docker integration"
)
async def test_real_docker_isolation_and_timeout(tmp_path):
    artifacts = Path("runs/m3-development/docker-smoke").resolve()
    sandbox = DockerSandbox(artifacts)
    source = tmp_path / "repo"
    source.mkdir()
    (source / ".env").write_text("DO_NOT_EXPOSE")
    (source / ".git").write_text("DO_NOT_EXPOSE")
    (source / "sample.py").write_text("x=1\n")
    build = await sandbox.build(
        "FROM python:3.12-slim\nWORKDIR /workspace\nCOPY . /workspace/\n", source
    )
    (artifacts / "smoke-build.json").write_text(
        json.dumps(build.model_dump() | sandbox.last_build, indent=2)
    )
    assert build.exit_code == 0, build.stderr
    check = """import os,pathlib
assert os.getuid()==65534
assert not pathlib.Path('.git').exists() and not pathlib.Path('.env').exists()
assert not any('API_KEY' in k for k in os.environ)
try:
    pathlib.Path('sample.py').write_text('bad')
except OSError:
    pass
else:
    raise AssertionError('source is writable')
pathlib.Path('/results/proof.txt').write_text('isolated')
print('uid=65534; metadata absent; source readonly; output writable')
"""
    result = await sandbox.run(("python", "-c", check), source, 20)
    (artifacts / "smoke-run.json").write_text(json.dumps(result.model_dump(), indent=2))
    assert result.exit_code == 0, result.stderr
    assert (Path(sandbox.last_run["output_directory"]) / "proof.txt").read_text() == "isolated"
    timeout = await sandbox.run(("python", "-c", "import time; time.sleep(60)"), source, 1)
    (artifacts / "smoke-timeout.json").write_text(json.dumps(timeout.model_dump(), indent=2))
    assert timeout.timed_out
    inspect = await sandbox.cli("inspect", sandbox.last_run["container"])
    assert inspect.exit_code != 0


async def test_docker_tests_do_not_fall_back_to_host(context, monkeypatch):
    from tools.factory import build_registry

    context.trusted_local = False
    context.docker = DockerSandbox(context.tracer.directory / "environment")

    async def forbidden(*args, **kwargs):
        raise AssertionError("external code must not execute on host")

    monkeypatch.setattr("sandbox.local.LocalSandbox.run", forbidden)
    registry = build_registry(context)
    assert "build_environment" in registry.tools
    result = await registry.call("run_tests", {})
    assert result.data["launch_error"] == "ENVIRONMENT_NOT_READY"
    assert not context.state.current_tests_passed
