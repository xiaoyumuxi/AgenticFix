"""Provider-neutral model contract and non-streaming Chat Completions transport."""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

PROVIDER_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "claude": "https://api.anthropic.com/v1",
}


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider: Literal["deepseek", "openai", "gemini", "qwen", "claude", "compatible"] = "deepseek"
    model: str | None = None
    base_url: str | None = None
    api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    timeout: float = Field(default=90, gt=0)
    token_parameter: Literal["max_tokens", "max_completion_tokens"] | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)
    extra_headers: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    max_response_bytes: int = Field(default=2_097_152, gt=0)

    @model_validator(mode="after")
    def defaults_and_validation(self) -> "ModelConfig":
        if not self.base_url:
            self.base_url = PROVIDER_URLS.get(self.provider)
        if not self.base_url:
            raise ValueError("compatible provider requires model_base_url")
        url = urlsplit(self.base_url)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Model base URL must not contain credentials, query or fragment")
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if url.scheme != "https" and not (url.scheme == "http" and local):
            raise ValueError("Use HTTPS (HTTP is allowed only for loopback model servers)")
        self.base_url = self.base_url.rstrip("/")
        if self.base_url.endswith("/chat/completions"):
            raise ValueError("Set the API base URL, not the chat/completions endpoint")
        if not self.model:
            if self.provider == "deepseek":
                self.model = "deepseek-flash"
            else:
                raise ValueError("Set model_name explicitly for this provider")
        if not self.token_parameter:
            self.token_parameter = (
                "max_completion_tokens" if self.provider == "openai" else "max_tokens"
            )
        reserved = {
            "model",
            "messages",
            "tools",
            "tool_choice",
            "stream",
            "n",
            "max_tokens",
            "max_completion_tokens",
        }
        if reserved.intersection(self.extra_body):
            raise ValueError("extra_body cannot override routing, tools or token limits")
        allowed_headers = {
            "anthropic-workspace-id",
            "openai-organization",
            "openai-project",
            "http-referer",
            "x-title",
        }
        if any(k.lower() not in allowed_headers for k in self.extra_headers):
            raise ValueError(
                "Unsupported extra header; authentication is controlled by the adapter"
            )
        return self

    def require_key(self) -> None:
        if not self.api_key.get_secret_value().strip():
            raise ValueError("Set AGENTICFIX_MODEL_API_KEY in local .env before model execution")

    def public_info(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "token_parameter": self.token_parameter,
        }


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    name: str = Field(min_length=1)
    arguments: str


class ModelToolCall(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    id: str = Field(min_length=1)
    type: Literal["function"] = "function"
    function: FunctionCall


class AssistantMessage(BaseModel):
    # Preserve provider extensions (DeepSeek reasoning_content, Gemini thought signatures).
    model_config = ConfigDict(extra="allow", strict=True)
    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[ModelToolCall] | None = None


class Usage(BaseModel):
    model_config = ConfigDict(strict=True)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def consistent(self) -> "Usage":
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError("Inconsistent usage")
        return self


class ModelReply(BaseModel):
    message: AssistantMessage
    finish_reason: str
    usage: Usage | None = None
    response_id: str | None = None
    model: str | None = None


class ModelError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LLMClient(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> ModelReply: ...


class OpenAICompatibleClient(LLMClient):
    def __init__(self, config: ModelConfig, *, transport: httpx.AsyncBaseTransport | None = None):
        config.require_key()
        self.config = config
        self.client = httpx.AsyncClient(
            timeout=config.timeout,
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> ModelReply:
        config = self.config
        payload = config.extra_body | {
            "model": config.model,
            "messages": messages,
            "tools": [{"type": "function", "function": tool} for tool in tools],
            "tool_choice": "auto",
            "stream": False,
            str(config.token_parameter): max_tokens,
        }
        try:
            async with asyncio.timeout(config.timeout):
                async with self.client.stream(
                    "POST",
                    f"{config.base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {config.api_key.get_secret_value()}",
                        **{k: v.get_secret_value() for k, v in config.extra_headers.items()},
                    },
                ) as response:
                    if response.status_code >= 300:
                        # Never include server error bodies, headers or credentials in logs.
                        raise ModelError(
                            f"HTTP_{response.status_code}",
                            retryable=(
                                response.status_code in {408, 429} or response.status_code >= 500
                            ),
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > config.max_response_bytes:
                            raise ModelError("RESPONSE_TOO_LARGE")
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelError("MODEL_TIMEOUT", retryable=True) from exc
        except httpx.TransportError as exc:
            raise ModelError("MODEL_CONNECTION_ERROR", retryable=True) from exc
        try:
            body = json.loads(raw)
            choices = body["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("Expected one choice")
            message = AssistantMessage.model_validate(choices[0]["message"])
            calls = message.tool_calls or []
            if len({call.id for call in calls}) != len(calls):
                raise ValueError("Duplicate tool IDs")
            finish = choices[0]["finish_reason"]
            if not isinstance(finish, str):
                raise ValueError("Missing finish reason")
            usage = None
            if body.get("usage") is not None:
                try:
                    usage = Usage.model_validate(body["usage"])
                except ValueError:
                    pass  # Explicitly unknown; runtime charges its reservation.
            return ModelReply(
                message=message,
                finish_reason=finish,
                usage=usage,
                response_id=body.get("id"),
                model=body.get("model"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelError("MALFORMED_RESPONSE", retryable=True) from exc
