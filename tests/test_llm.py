import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agent.llm import ModelConfig, ModelError, OpenAICompatibleClient


def response(message=None, *, usage=True, finish="stop"):
    body = {
        "id": "mock-response",
        "choices": [
            {
                "message": message
                or {
                    "role": "assistant",
                    "content": "Finished",
                },
                "finish_reason": finish,
            }
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    return body


@pytest.mark.parametrize(
    "provider,base,parameter",
    [
        ("deepseek", "https://api.deepseek.com", "max_tokens"),
        ("openai", "https://api.openai.com/v1", "max_completion_tokens"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "max_tokens"),
        ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "max_tokens"),
        ("claude", "https://api.anthropic.com/v1", "max_tokens"),
        ("compatible", "http://localhost:8000/v1", "max_tokens"),
    ],
)
async def test_provider_payloads(provider, base, parameter):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    config = ModelConfig(
        provider=provider,
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url=base,
        extra_body={"temperature": 0.2},
    )
    client = OpenAICompatibleClient(config, transport=httpx.MockTransport(handler))
    try:
        reply = await client.generate(
            [{"role": "user", "content": "task"}],
            [
                {"name": "read_file", "description": "read", "parameters": {"type": "object"}},
            ],
            123,
        )
    finally:
        await client.aclose()
    request = requests[0]
    assert str(request.url) == base + "/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    payload = json.loads(request.content)
    assert payload[parameter] == 123
    assert payload["stream"] is False
    assert payload["tools"][0]["function"]["name"] == "read_file"
    assert payload["temperature"] == 0.2
    assert reply.usage.total_tokens == 15
    assert "test-key" not in repr(config)
    assert "api_key" not in config.public_info()


async def test_reasoning_and_provider_extensions_round_trip():
    message = {
        "role": "assistant",
        "content": None,
        "reasoning_content": "opaque provider state",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"a.py"}'},
                "extra_content": {"google": {"thought_signature": "opaque-signature"}},
            }
        ],
    }
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response(message, finish="tool_calls"))

    client = OpenAICompatibleClient(
        ModelConfig(api_key=SecretStr("key")), transport=httpx.MockTransport(handler)
    )
    try:
        reply = await client.generate([], [], 100)
        await client.generate(
            [
                reply.message.model_dump(exclude_none=True),
                {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
            ],
            [],
            100,
        )
    finally:
        await client.aclose()
    echoed = requests[1]["messages"][0]
    assert echoed["reasoning_content"] == message["reasoning_content"]
    assert (
        echoed["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
        == "opaque-signature"
    )
    assert ModelConfig().model == "deepseek-flash"


@pytest.mark.parametrize(
    "status,retryable",
    [(401, False), (403, False), (400, False), (429, True), (503, True), (302, False)],
)
async def test_http_errors_do_not_leak_body(status, retryable):
    client = OpenAICompatibleClient(
        ModelConfig(api_key=SecretStr("key")),
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text="secret-error")),
    )
    try:
        with pytest.raises(ModelError) as exc:
            await client.generate([], [], 10)
    finally:
        await client.aclose()
    assert exc.value.code == f"HTTP_{status}"
    assert exc.value.retryable is retryable
    assert "secret-error" not in str(exc.value)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        response({"role": "user", "content": "bad"}),
        response(
            {
                "role": "assistant",
                "content": "bad",
                "tool_calls": [
                    {"id": "x", "function": {"name": "read_file", "arguments": "{}"}},
                    {"id": "x", "function": {"name": "read_file", "arguments": "{}"}},
                ],
            }
        ),
    ],
)
async def test_malformed_envelopes(body):
    client = OpenAICompatibleClient(
        ModelConfig(api_key=SecretStr("key")),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    try:
        with pytest.raises(ModelError, match="MALFORMED_RESPONSE"):
            await client.generate([], [], 10)
    finally:
        await client.aclose()


async def test_unknown_usage_timeout_and_response_limit():
    client = OpenAICompatibleClient(
        ModelConfig(api_key=SecretStr("key")),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response(usage=False))
        ),
    )
    try:
        assert (await client.generate([], [], 10)).usage is None
    finally:
        await client.aclose()

    def timeout(request):
        raise httpx.ReadTimeout("secret url", request=request)

    client = OpenAICompatibleClient(
        ModelConfig(api_key=SecretStr("key")), transport=httpx.MockTransport(timeout)
    )
    try:
        with pytest.raises(ModelError, match="MODEL_TIMEOUT"):
            await client.generate([], [], 10)
    finally:
        await client.aclose()
    client = OpenAICompatibleClient(
        ModelConfig(api_key=SecretStr("key"), max_response_bytes=10),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="x" * 100)),
    )
    try:
        with pytest.raises(ModelError, match="RESPONSE_TOO_LARGE"):
            await client.generate([], [], 10)
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "config",
    [
        {"provider": "compatible"},
        {"provider": "openai"},
        {"base_url": "https://key:secret@example.com"},
        {"base_url": "http://example.com"},
        {"base_url": "https://example.com?api_key=key"},
        {"extra_body": {"messages": []}},
        {"extra_body": {"max_tokens": 99999}},
    ],
)
def test_config_rejects_unsafe_or_incomplete_options(config):
    with pytest.raises(ValidationError):
        ModelConfig(**config)


def test_missing_key_is_explicit():
    with pytest.raises(ValueError, match="AGENTICFIX_MODEL_API_KEY"):
        OpenAICompatibleClient(ModelConfig())


async def test_workspace_headers_and_validation_redact_secrets():
    seen = []

    def handler(request):
        seen.append(request.headers)
        return httpx.Response(200, json=response())

    config = ModelConfig(
        provider="claude",
        model="test-model",
        api_key=SecretStr("key"),
        extra_headers={"anthropic-workspace-id": SecretStr("workspace-123")},
    )
    client = OpenAICompatibleClient(config, transport=httpx.MockTransport(handler))
    try:
        await client.generate([], [], 10)
    finally:
        await client.aclose()
    assert seen[0]["anthropic-workspace-id"] == "workspace-123"
    assert "workspace-123" not in repr(config)
    with pytest.raises(ValidationError) as exc:
        ModelConfig(base_url="https://key:private-secret@example.com")
    assert "private-secret" not in str(exc.value)
    with pytest.raises(ValidationError):
        ModelConfig(extra_headers={"Authorization": SecretStr("override")})
