from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field


class ExecutionResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration: float
    timed_out: bool = False
    truncated: bool = False
    launch_error: str | None = None
    diagnostic_lines: list[str] = Field(default_factory=list)


class Sandbox(ABC):
    @abstractmethod
    async def run(self, argv: tuple[str, ...], cwd: Path, timeout: float) -> ExecutionResult: ...
