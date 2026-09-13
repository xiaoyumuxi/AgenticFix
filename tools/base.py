from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from tools.context import ToolContext


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error: str | None = None
    truncated: bool = False
    fatal: bool = False


class ToolError(Exception):
    def __init__(self, code: str, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.fatal = fatal


class BaseTool(ABC):
    name: str
    description: str
    args_schema: type[ToolArgs]

    @abstractmethod
    async def execute(self, args: ToolArgs, context: "ToolContext") -> ToolResult: ...
