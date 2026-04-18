from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.errors import LLMResponseParseError
from app.llm.models import (
    LLMJsonSchema,
    LLMMessage,
    LLMRequest,
    LLMRequestOptions,
    LLMResponse,
    LLMResponseFormat,
    LLMResponseFormatType,
)
from app.llm.providers.base import BaseLLMProvider

StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)


class LLMClient:
    """Provider-agnostic entry point used by future enrichment and report workflows."""

    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider

    def generate(self, request: LLMRequest) -> LLMResponse:
        return self.provider.generate(request)

    def generate_text(
        self,
        *,
        messages: list[LLMMessage],
        model: str | None = None,
        task_name: str = "text_generation",
        options: LLMRequestOptions | None = None,
    ) -> str:
        response = self.generate(
            LLMRequest(
                task_name=task_name,
                messages=messages,
                model=model,
                options=options or LLMRequestOptions(),
            )
        )
        return response.message.content

    def generate_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type[StructuredModelT],
        model: str | None = None,
        task_name: str = "structured_generation",
        options: LLMRequestOptions | None = None,
    ) -> StructuredModelT:
        request_options = (
            options.model_copy(deep=True) if options is not None else LLMRequestOptions()
        )
        request_options.response_format = LLMResponseFormat(
            type=LLMResponseFormatType.JSON_SCHEMA,
            json_schema=LLMJsonSchema(
                name=task_name,
                schema_definition=_normalize_strict_json_schema(
                    response_model.model_json_schema()
                ),
                description=response_model.__doc__,
                strict=True,
            ),
        )

        response = self.generate(
            LLMRequest(
                task_name=task_name,
                messages=messages,
                model=model,
                options=request_options,
            )
        )
        return self._parse_structured_response(response, response_model, task_name)

    def _parse_structured_response(
        self,
        response: LLMResponse,
        response_model: type[StructuredModelT],
        task_name: str,
    ) -> StructuredModelT:
        try:
            payload = json.loads(response.message.content)
        except json.JSONDecodeError as exc:
            raise LLMResponseParseError(
                "LLM returned invalid JSON for a structured generation request.",
                details={
                    "provider": response.provider.value,
                    "model": response.model,
                    "task_name": task_name,
                },
            ) from exc

        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            raise LLMResponseParseError(
                "LLM returned JSON that does not match the requested schema.",
                details={
                    "provider": response.provider.value,
                    "model": response.model,
                    "task_name": task_name,
                    "validation_errors": exc.errors(),
                },
            ) from exc


def _normalize_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Make Pydantic JSON Schema acceptable to strict structured-output providers.

    OpenAI-compatible strict schemas require fixed-shape objects to opt out of extra
    fields with ``additionalProperties: false``. Pydantic does not emit that for plain
    models by default, so we recursively add it before sending the schema upstream.
    """

    normalized = deepcopy(schema)
    _normalize_json_schema_node(normalized)
    return normalized


def _normalize_json_schema_node(node: Any) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        additional_properties = node.get("additionalProperties")

        # Only force closed-world semantics for fixed-shape objects. If a schema already
        # uses ``additionalProperties`` to model a free-form map, we keep that contract.
        if node.get("type") == "object" and isinstance(properties, dict):
            node["additionalProperties"] = False
            node["required"] = list(properties.keys())
        elif (
            node.get("type") == "object"
            and not properties
            and additional_properties is None
        ):
            node["additionalProperties"] = False
            node["required"] = []

        for value in node.values():
            _normalize_json_schema_node(value)
        return

    if isinstance(node, list):
        for item in node:
            _normalize_json_schema_node(item)
