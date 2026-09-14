"""Host-owned configuration; tool arguments cannot replace execution policy."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.llm import ModelConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTICFIX_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    cache_dir: Path = Path(".cache/repositories")
    worktree_dir: Path = Path(".worktrees")
    runs_dir: Path = Path("runs")
    max_file_bytes: int = Field(default=1_048_576, ge=1)
    max_read_lines: int = Field(default=400, ge=1)
    max_build_timeout: float = Field(default=300, gt=0, le=900)
    environment_prompt_version: str = "environment-v1"
    max_test_timeout: float = Field(default=60, gt=0)
    max_output_bytes: int = Field(default=1_048_576, ge=1)
    max_entries: int = Field(default=2000, ge=1)
    max_scan_entries: int = Field(default=20000, ge=1)

    model_provider: str = "deepseek"
    model_name: str | None = None
    model_base_url: str | None = None
    model_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    model_timeout: float = Field(default=90, gt=0)
    model_token_parameter: str | None = None
    model_extra_headers: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    model_extra_body: dict[str, object] = Field(default_factory=dict)
    max_iterations: int = Field(default=30, ge=1)
    max_tool_calls: int = Field(default=60, ge=1)
    max_token_budget: int = Field(default=100000, ge=1)
    max_completion_tokens: int = Field(default=4096, ge=1)
    max_run_duration: float = Field(default=600, gt=0)
    max_model_retries: int = Field(default=2, ge=0, le=5)
    retry_delay: float = Field(default=1, ge=0, le=10)
    max_context_bytes: int = Field(default=150000, ge=100)
    max_tool_message_chars: int = Field(default=12000, ge=200)
    compact_successful_build: bool = False
    retained_read_results: int | None = Field(default=None, ge=1)
    max_repeated_actions: int = Field(default=3, ge=1)

    def llm_config(self) -> ModelConfig:
        return ModelConfig.model_validate(
            {
                "provider": self.model_provider,
                "model": self.model_name,
                "base_url": self.model_base_url,
                "api_key": self.model_api_key,
                "timeout": self.model_timeout,
                "token_parameter": self.model_token_parameter,
                "extra_body": self.model_extra_body,
                "extra_headers": self.model_extra_headers,
            }
        )
