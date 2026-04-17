from __future__ import annotations

import json
from typing import Any

import httpx

from app.llm.errors import (
    LLMConfigurationError,
    LLMProviderRequestError,
    LLMResponseParseError,
)
from app.llm.models import (
    LLMMessage,
    LLMMessageRole,
    LLMProviderName,
    LLMRequest,
    LLMResponse,
    LLMResponseFormatType,
    LLMUsage,
)
from app.llm.providers.base import BaseLLMProvider


class OpenRouterProvider(BaseLLMProvider):
    provider_name = LLMProviderName.OPENROUTER

    def __init__(
        self,
        *,
        api_key: str | None,
        default_model: str | None,
        base_url: str,
        timeout_seconds: float,
        app_url: str | None = None,
        app_title: str | None = None,
        enable_response_healing: bool = True,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self.app_url = app_url
        self.app_title = app_title
        self.enable_response_healing = enable_response_healing
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.default_model
        if not self.api_key:
            raise LLMConfigurationError(
                "LLM API key is not configured.",
                details={"provider": self.provider_name.value},
            )
        if not model:
            raise LLMConfigurationError(
                "LLM default model is not configured.",
                details={"provider": self.provider_name.value},
            )

        payload = self._build_payload(request, model)
        headers = self._build_headers()

        try:
            response = self.http_client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMProviderRequestError(
                "LLM provider rejected the request.",
                details={
                    "provider": self.provider_name.value,
                    "model": model,
                    "task_name": request.task_name,
                    "status_code": exc.response.status_code,
                    "response_body": exc.response.text[:1000],
                },
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderRequestError(
                "LLM provider request failed.",
                details={
                    "provider": self.provider_name.value,
                    "model": model,
                    "task_name": request.task_name,
                    "reason": str(exc),
                },
            ) from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseParseError(
                "LLM provider returned a non-JSON response.",
                details={
                    "provider": self.provider_name.value,
                    "model": model,
                    "task_name": request.task_name,
                },
            ) from exc

        return self._parse_response(data, requested_model=model, task_name=request.task_name)

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.app_url:
            headers["HTTP-Referer"] = self.app_url
        if self.app_title:
            headers["X-Title"] = self.app_title
        return headers

    def _build_payload(self, request: LLMRequest, model: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                message.model_dump(mode="json", exclude_none=True)
                for message in request.messages
            ],
        }
        options = request.options
        if options.temperature is not None:
            payload["temperature"] = options.temperature
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        if options.top_p is not None:
            payload["top_p"] = options.top_p
        if options.stop:
            payload["stop"] = options.stop
        if options.seed is not None:
            payload["seed"] = options.seed

        response_format = options.response_format
        if response_format.type == LLMResponseFormatType.JSON_OBJECT:
            payload["response_format"] = {"type": "json_object"}
        elif response_format.type == LLMResponseFormatType.JSON_SCHEMA:
            assert response_format.json_schema is not None
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": response_format.json_schema.model_dump(
                    mode="json",
                    exclude_none=True,
                    by_alias=True,
                ),
            }
            if self.enable_response_healing:
                # Structured outputs are likely to be reused across multiple backend tasks,
                # so we enable response healing to reduce JSON parsing flakiness.
                payload["plugins"] = [{"id": "response-healing"}]

        return payload

    def _parse_response(
        self,
        data: dict[str, Any],
        *,
        requested_model: str,
        task_name: str,
    ) -> LLMResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseParseError(
                "LLM provider returned no completion choices.",
                details={
                    "provider": self.provider_name.value,
                    "model": requested_model,
                    "task_name": task_name,
                },
            )

        first_choice = choices[0]
        message_payload = first_choice.get("message") or {}
        content = self._extract_message_content(message_payload.get("content"))
        if content is None:
            raise LLMResponseParseError(
                "LLM provider returned a completion without text content.",
                details={
                    "provider": self.provider_name.value,
                    "model": requested_model,
                    "task_name": task_name,
                },
            )

        usage = data.get("usage")
        return LLMResponse(
            provider=self.provider_name,
            provider_request_id=data.get("id"),
            model=str(data.get("model") or requested_model),
            finish_reason=first_choice.get("finish_reason"),
            message=LLMMessage(
                role=message_payload.get("role", LLMMessageRole.ASSISTANT),
                content=content,
                name=message_payload.get("name"),
            ),
            usage=LLMUsage.model_validate(usage) if isinstance(usage, dict) else None,
            raw_response=data,
        )

    def _extract_message_content(self, content: Any) -> str | None:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return None

        # Some providers return multipart content blocks. We only keep text-like chunks here
        # because later report generation and data-enhancement flows need a plain text contract.
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
                continue
            if isinstance(part.get("content"), str):
                text_parts.append(part["content"])

        joined = "\n".join(part for part in text_parts if part.strip())
        return joined or None
