from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from app.infra.settings import Settings
from app.llm import (
    LLMClient,
    LLMConfigurationError,
    LLMMessage,
    LLMMessageRole,
    LLMProviderRequestError,
    LLMRequest,
    LLMRequestOptions,
    LLMResponse,
    LLMResponseFormat,
    LLMResponseFormatType,
    LLMResponseParseError,
    LLMUsage,
    OpenRouterProvider,
    build_llm_client,
)


class TrialSignal(BaseModel):
    """Structured enrichment result for one evidence selection."""

    label: str
    confidence: float


class EvidencePoint(BaseModel):
    field_name: str
    excerpt: str


class NestedSignal(BaseModel):
    summary: str
    evidence: list[EvidencePoint]


def test_openrouter_provider_builds_expected_request_payload() -> None:
    captured_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "resp-1",
                "model": "openai/gpt-4o-mini",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                },
            },
        )

    provider = OpenRouterProvider(
        api_key="test-key",
        default_model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=30,
        app_url="https://example.com",
        app_title="MIS Test",
        enable_response_healing=True,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = provider.generate(
        LLMRequest(
            task_name="report_outline",
            messages=[
                LLMMessage(role=LLMMessageRole.SYSTEM, content="You are a precise analyst."),
                LLMMessage(role=LLMMessageRole.USER, content="Summarize HER2 activity."),
            ],
            options=LLMRequestOptions(
                temperature=0.2,
                max_tokens=256,
            ),
        )
    )

    assert captured_request["url"] == "https://openrouter.ai/api/v1/chat/completions"
    headers = captured_request["headers"]
    assert headers["authorization"] == "Bearer test-key"
    assert headers["http-referer"] == "https://example.com"
    assert headers["x-title"] == "MIS Test"
    assert captured_request["body"] == {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a precise analyst."},
            {"role": "user", "content": "Summarize HER2 activity."},
        ],
        "temperature": 0.2,
        "max_tokens": 256,
    }
    assert response.message.content == "ok"
    assert response.usage == LLMUsage(
        prompt_tokens=10,
        completion_tokens=3,
        total_tokens=13,
    )


def test_openrouter_provider_enables_response_healing_for_structured_output() -> None:
    captured_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "resp-2",
                "model": "openai/gpt-4o-mini",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"label":"late-stage","confidence":0.91}',
                        },
                    }
                ],
            },
        )

    provider = OpenRouterProvider(
        api_key="test-key",
        default_model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=30,
        enable_response_healing=True,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    provider.generate(
        LLMRequest(
            task_name="trial_signal",
            messages=[LLMMessage(role=LLMMessageRole.USER, content="Return JSON only.")],
            options=LLMRequestOptions(
                response_format=LLMResponseFormat(
                    type=LLMResponseFormatType.JSON_SCHEMA,
                    json_schema={
                        "name": "trial_signal",
                        "schema": TrialSignal.model_json_schema(),
                        "strict": True,
                    },
                )
            ),
        )
    )

    body = captured_request["body"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "trial_signal"
    assert body["plugins"] == [{"id": "response-healing"}]


def test_llm_client_generate_structured_validates_schema() -> None:
    provider = StubProvider(
        response=LLMResponse(
            provider="openrouter",
            provider_request_id="resp-3",
            model="openai/gpt-4o-mini",
            finish_reason="stop",
            message=LLMMessage(
                role=LLMMessageRole.ASSISTANT,
                content='{"label":"late-stage","confidence":0.91}',
            ),
        )
    )
    client = LLMClient(provider)

    result = client.generate_structured(
        task_name="trial_signal",
        messages=[LLMMessage(role=LLMMessageRole.USER, content="Return JSON only.")],
        response_model=TrialSignal,
    )

    assert result == TrialSignal(label="late-stage", confidence=0.91)
    assert provider.last_request is not None
    schema = provider.last_request.options.response_format.json_schema.schema_definition
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["label", "confidence"]


def test_llm_client_generate_structured_normalizes_nested_object_schema() -> None:
    provider = StubProvider(
        response=LLMResponse(
            provider="openrouter",
            provider_request_id="resp-3b",
            model="openai/gpt-4o-mini",
            finish_reason="stop",
            message=LLMMessage(
                role=LLMMessageRole.ASSISTANT,
                content=(
                    '{"summary":"useful signal","evidence":'
                    '[{"field_name":"title","excerpt":"HER2 result"}]}'
                ),
            ),
        )
    )
    client = LLMClient(provider)

    result = client.generate_structured(
        task_name="nested_signal",
        messages=[LLMMessage(role=LLMMessageRole.USER, content="Return JSON only.")],
        response_model=NestedSignal,
    )

    assert result.summary == "useful signal"
    assert provider.last_request is not None
    schema = provider.last_request.options.response_format.json_schema.schema_definition
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["summary", "evidence"]
    assert schema["$defs"]["EvidencePoint"]["additionalProperties"] is False
    assert schema["$defs"]["EvidencePoint"]["required"] == ["field_name", "excerpt"]


def test_llm_client_generate_structured_rejects_invalid_json() -> None:
    provider = StubProvider(
        response=LLMResponse(
            provider="openrouter",
            provider_request_id="resp-4",
            model="openai/gpt-4o-mini",
            finish_reason="stop",
            message=LLMMessage(
                role=LLMMessageRole.ASSISTANT,
                content="not-json",
            ),
        )
    )
    client = LLMClient(provider)

    with pytest.raises(LLMResponseParseError):
        client.generate_structured(
            task_name="trial_signal",
            messages=[LLMMessage(role=LLMMessageRole.USER, content="Return JSON only.")],
            response_model=TrialSignal,
        )


def test_openrouter_provider_requires_api_key() -> None:
    provider = OpenRouterProvider(
        api_key=None,
        default_model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=30,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={})
            )
        ),
    )

    with pytest.raises(LLMConfigurationError):
        provider.generate(
            LLMRequest(
                messages=[LLMMessage(role=LLMMessageRole.USER, content="Hello")],
            )
        )


def test_build_llm_client_rejects_unknown_provider() -> None:
    settings = Settings(
        llm_provider="unknown",
        llm_api_key="test-key",
        llm_default_model="openai/gpt-4o-mini",
    )

    with pytest.raises(LLMConfigurationError):
        build_llm_client(settings)


def test_openrouter_provider_surfaces_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    provider = OpenRouterProvider(
        api_key="test-key",
        default_model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=30,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMProviderRequestError):
        provider.generate(
            LLMRequest(
                messages=[LLMMessage(role=LLMMessageRole.USER, content="Hello")],
            )
        )


class StubProvider:
    provider_name = "openrouter"

    def __init__(self, *, response: LLMResponse) -> None:
        self.response = response
        self.last_request: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return self.response
