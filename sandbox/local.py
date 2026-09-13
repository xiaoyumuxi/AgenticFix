import asyncio
import os
import signal
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from sandbox.base import ExecutionResult, Sandbox


class LocalSandbox(Sandbox):
    """Bounded POSIX process runner, NOT a security sandbox. Trusted fixtures only."""

    def __init__(self, *, trusted: bool, max_output_bytes: int) -> None:
        if not trusted:
            raise ValueError("LocalSandbox requires an explicitly trusted fixture")
        self.max_output_bytes = max_output_bytes

    async def run(self, argv: tuple[str, ...], cwd: Path, timeout: float) -> ExecutionResult:
        started = time.monotonic()
        # Do not pass provider tokens and unrelated user environment to test processes.
        env = {
            k: os.environ[k]
            for k in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
            if k in os.environ
        }
        env.update(
            {
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONIOENCODING": "utf-8",
                # A fresh unused prefix avoids stale same-second, same-size source bytecode.
                # Disable writes so no cache directory needs to be created or cleaned.
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(
                    Path(tempfile.gettempdir()) / f"agenticfix-{uuid4().hex}"
                ),
            }
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            return ExecutionResult(
                duration=time.monotonic() - started, launch_error=type(exc).__name__
            )
        output: list[bytearray] = [bytearray(), bytearray()]
        truncated = False

        async def drain(reader: asyncio.StreamReader | None, target: bytearray) -> None:
            nonlocal truncated
            assert reader is not None
            while chunk := await reader.read(65536):
                remaining = max(0, self.max_output_bytes - len(target))
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated = True

        def kill_group() -> None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        drains = [
            asyncio.create_task(drain(process.stdout, output[0])),
            asyncio.create_task(drain(process.stderr, output[1])),
        ]
        timed_out = False
        try:
            async with asyncio.timeout(timeout):
                await process.wait()
                # Descendants must not survive a completed test command or hold pipes open.
                kill_group()
                await asyncio.gather(*drains)
        except TimeoutError:
            timed_out = True
            kill_group()
            await process.wait()
            await asyncio.gather(*drains)
        except asyncio.CancelledError:
            kill_group()
            await process.wait()
            await asyncio.gather(*drains)
            raise
        return ExecutionResult(
            stdout=output[0].decode("utf-8", errors="replace"),
            stderr=output[1].decode("utf-8", errors="replace"),
            exit_code=process.returncode,
            duration=time.monotonic() - started,
            timed_out=timed_out,
            truncated=truncated,
        )
