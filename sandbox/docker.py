"""Host-controlled Docker CLI; repository commands run only inside containers."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Any
from uuid import uuid4

from sandbox.base import ExecutionResult, Sandbox

EXCLUDED = {
    ".git",
    ".env",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".dockerignore",
}


def snapshot(source: Path, destination: Path) -> None:
    """Copy regular files only; never expose Git metadata, secrets or host links."""
    total = 0
    for directory, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [d for d in dirs if d not in EXCLUDED and not d.startswith(".env.")]
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f"Unsupported repository symlink: {path.relative_to(source)}")
        relative = Path(directory).relative_to(source)
        (destination / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in EXCLUDED or name.startswith(".env."):
                continue
            path = Path(directory) / name
            if not path.is_file() or path.stat().st_nlink > 1:
                raise ValueError("Only regular non-hardlinked repository files are supported")
            total += path.stat().st_size
            if total > 50_000_000:
                raise ValueError("Repository snapshot exceeds 50 MB")
            target = destination / relative / name
            shutil.copyfile(path, target)
            target.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)


def validate_dockerfile(text: str) -> None:
    if len(text.encode()) > 24000 or "\0" in text:
        raise ValueError("Dockerfile exceeds text limits")
    if any(
        line.lstrip().lower().startswith(("# syntax", "# escape")) for line in text.splitlines()
    ):
        raise ValueError("Custom Dockerfile frontends/escape directives are not allowed")
    lines = text.replace("\\\n", " ").splitlines()
    instructions = [
        line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]
    if not instructions or not instructions[0].startswith("FROM "):
        raise ValueError("Start with FROM python:3.<10-14>-slim")
    from_count = 0
    for line in instructions:
        command, _, value = line.partition(" ")
        if command not in {"FROM", "WORKDIR", "COPY", "RUN", "ENV", "CMD", "LABEL", "USER"}:
            raise ValueError(f"Unsupported Dockerfile instruction: {command}")
        if command == "FROM":
            from_count += 1
            if not re.fullmatch(
                r"python:3\.(10|11|12|13|14)-slim(?:-bookworm|-trixie)?(?:@sha256:[a-f0-9]{64})?",
                value,
            ):
                raise ValueError("Choose a supported official Python slim image")
        if command == "COPY" and value not in {". .", ". /workspace", ". /workspace/", ". ./"}:
            raise ValueError("COPY must copy the supplied repository: COPY . /workspace/")
        if command == "WORKDIR" and value != "/workspace":
            raise ValueError("Use WORKDIR /workspace")
        if command == "RUN" and value.startswith("--"):
            raise ValueError("RUN flags/mounts are not exposed")
    if from_count != 1:
        raise ValueError("This milestone supports single-stage images")


class DockerSandbox(Sandbox):
    def __init__(self, directory: Path, *, max_output_bytes: int = 1_048_576) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_output_bytes = max_output_bytes
        self.image_id: str | None = None
        self.build_number = 0
        self.cli_number = 0
        self.last_build: dict[str, Any] = {}
        self.last_run: dict[str, Any] = {}

    async def cli(self, *args: str, timeout: float = 60) -> ExecutionResult:
        start = time.monotonic()
        self.cli_number += 1
        cli_number = self.cli_number
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            in {"PATH", "HOME", "LANG", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"}
        }
        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                *args,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            return ExecutionResult(
                duration=time.monotonic() - start, launch_error=type(exc).__name__
            )
        buffers = [bytearray(), bytearray()]
        truncated = False
        stream_truncated = [False, False]
        candidates: deque[str] = deque(maxlen=16)
        pattern = re.compile(rb"error|exception|traceback|failed|not found|no module named", re.I)
        marker = b"\n...[middle omitted]...\n"

        async def drain(stream: asyncio.StreamReader | None, index: int) -> None:
            nonlocal truncated
            assert stream is not None
            buffer = buffers[index]
            pending = b""

            def inspect(line: bytes) -> None:
                match = pattern.search(line)
                if match:
                    start = max(0, match.start() - 80)
                    text = (
                        ("stdout" if index == 0 else "stderr")
                        + ": "
                        + line[start : start + 512].decode(errors="replace")
                    )
                    if text not in candidates:
                        candidates.append(text)

            while chunk := await stream.read(65536):
                lines = (pending + chunk).split(b"\n")
                for line in lines[:-1]:
                    inspect(line)
                # Bound an unterminated long line as well as the retained output.
                pending = lines[-1]
                if len(pending) > 2048:
                    inspect(pending)
                    pending = pending[-2048:]
                buffer.extend(chunk)
                if stream_truncated[index] or len(buffer) > self.max_output_bytes:
                    truncated = True
                    stream_truncated[index] = True
                    # Keep the first quarter and a rolling tail, within the byte cap.
                    retained = max(0, self.max_output_bytes - len(marker))
                    head = retained // 4
                    tail = retained - head
                    buffer[:] = buffer[:head] + (buffer[-tail:] if tail else b"")
            inspect(pending)

        tasks = [
            asyncio.create_task(drain(process.stdout, 0)),
            asyncio.create_task(drain(process.stderr, 1)),
        ]
        timed_out = False
        cancelled = False
        try:
            async with asyncio.timeout(timeout):
                await process.wait()
                await asyncio.gather(*tasks)
        except (TimeoutError, asyncio.CancelledError) as exc:
            import signal

            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            await asyncio.gather(*tasks)
            cancelled = isinstance(exc, asyncio.CancelledError)
            timed_out = not cancelled
        for index, was_truncated in enumerate(stream_truncated):
            if was_truncated:
                head = max(0, self.max_output_bytes - len(marker)) // 4
                buffers[index][head:head] = marker[: self.max_output_bytes]
        result = ExecutionResult(
            stdout=buffers[0].decode(errors="replace"),
            stderr=buffers[1].decode(errors="replace"),
            exit_code=process.returncode,
            duration=time.monotonic() - start,
            timed_out=timed_out,
            truncated=truncated,
            diagnostic_lines=list(candidates),
        )

        (self.directory / f"cli-{cli_number}.json").write_text(
            json.dumps(
                {
                    "argv": list(args),
                    "result": result.model_dump(),
                    "cancelled": cancelled,
                    "output_retention": "head quarter and rolling tail when truncated",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def build(self, dockerfile: str, source: Path, timeout: float = 300) -> ExecutionResult:
        validate_dockerfile(dockerfile)
        self.image_id = (
            None  # A failed rebuild must not fall back to a previously successful image.
        )
        self.build_number += 1
        prefix = f"build-{self.build_number}"
        (self.directory / f"{prefix}.Dockerfile").write_text(dockerfile)
        builder = f"agenticfix-{uuid4().hex[:12]}"
        tag = f"agenticfix:{uuid4().hex[:12]}"
        started = time.monotonic()
        self.last_build = {
            "dockerfile_sha256": hashlib.sha256(dockerfile.encode()).hexdigest(),
            "builder": builder,
            "cache": "fresh builder; --no-cache",
            "tag": tag,
        }
        try:
            with tempfile.TemporaryDirectory(prefix="agenticfix-build-") as temp:
                context = Path(temp)
                snapshot(source, context)
                (context / "AgenticFix.Dockerfile").write_text(dockerfile)
                created = await self.cli(
                    "buildx",
                    "create",
                    "--name",
                    builder,
                    "--driver",
                    "docker-container",
                    "--driver-opt",
                    "memory=2g,memory-swap=2g,cpu-period=100000,cpu-quota=200000",
                    timeout=30,
                )
                if created.exit_code != 0:
                    return created
                metadata = self.directory / f"{prefix}-image.json"
                result = await self.cli(
                    "buildx",
                    "build",
                    "--builder",
                    builder,
                    "--load",
                    "--no-cache",
                    "--progress",
                    "plain",
                    "--provenance=false",
                    "--metadata-file",
                    str(metadata),
                    "-t",
                    tag,
                    "-f",
                    str(context / "AgenticFix.Dockerfile"),
                    str(context),
                    timeout=timeout,
                )
                if result.exit_code == 0 and not result.timed_out:
                    inspection = await self.cli("image", "inspect", tag, timeout=30)
                    if inspection.exit_code != 0:
                        return inspection
                    info = json.loads(inspection.stdout)[0]
                    self.image_id = info["Id"]
                    self.last_build["image_id"] = self.image_id
                    self.last_build["image_config"] = info["Config"]
                return result
        finally:
            cleanup = await self.cli("buildx", "rm", "--force", builder, timeout=30)
            self.last_build["cleanup_exit_code"] = cleanup.exit_code
            self.last_build["total_duration"] = time.monotonic() - started

    async def run(self, argv: tuple[str, ...], cwd: Path, timeout: float) -> ExecutionResult:
        if not self.image_id:
            return ExecutionResult(duration=0, launch_error="ENVIRONMENT_NOT_READY")
        name = f"agenticfix-test-{uuid4().hex[:12]}"
        output = self.directory / name
        output.mkdir(mode=0o777)
        output.chmod(0o777)
        self.last_run = {
            "image_id": self.image_id,
            "container": name,
            "output_directory": str(output),
        }
        try:
            with tempfile.TemporaryDirectory(prefix="agenticfix-test-") as temp:
                source = Path(temp) / "source"
                snapshot(cwd, source)
                return await self.cli(
                    "run",
                    "--rm",
                    "--name",
                    name,
                    "--network=none",
                    "--memory=1g",
                    "--memory-swap=1g",
                    "--cpus=2",
                    "--pids-limit=128",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--read-only",
                    "--user=65534:65534",
                    "--tmpfs=/tmp:rw,nosuid,size=128m",
                    "--mount",
                    f"type=bind,src={source},dst=/workspace,readonly",
                    "--mount",
                    f"type=bind,src={output},dst=/results",
                    "--workdir=/workspace",
                    "--env=PYTHONDONTWRITEBYTECODE=1",
                    "--env=PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
                    "--env=PYTHONPATH=/workspace",
                    "--env=HOME=/tmp",
                    "--entrypoint",
                    argv[0],
                    self.image_id,
                    *argv[1:],
                    timeout=timeout,
                )
        finally:
            await self.cli("rm", "-f", name, timeout=15)
