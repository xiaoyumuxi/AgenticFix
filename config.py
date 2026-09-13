"""Host-owned configuration; tool arguments cannot replace execution policy."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTICFIX_", env_file=".env", extra="ignore")

    cache_dir: Path = Path(".cache/repositories")
    worktree_dir: Path = Path(".worktrees")
    runs_dir: Path = Path("runs")
    max_file_bytes: int = Field(default=1_048_576, ge=1)
    max_read_lines: int = Field(default=400, ge=1)
    max_test_timeout: float = Field(default=60, gt=0)
    max_output_bytes: int = Field(default=1_048_576, ge=1)
    max_entries: int = Field(default=2000, ge=1)
    max_scan_entries: int = Field(default=20000, ge=1)
