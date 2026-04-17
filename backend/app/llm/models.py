from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMProviderName(str, Enum):
    OPENROUTER = "openrouter"


class LLMMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMResponseFormatType(str, Enum):
    TEXT = "text"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


class LLMJsonSchema(BaseModel):
    """Represents a strict schema contract for structured model outputs."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    schema_definition: dict[str, Any] = Field(alias="schema")
    description: str | None = None
    strict: bool = True


class LLMResponseFormat(BaseModel):
    type: LLMResponseFormatType = LLMResponseFormatType.TEXT
    json_schema: LLMJsonSchema | None = None

    @model_validator(mode="after")
    def validate_json_schema_configuration(self) -> "LLMResponseFormat":
        if self.type == LLMResponseFormatType.JSON_SCHEMA and self.json_schema is None:
            raise ValueError("json_schema must be provided when type is json_schema.")
        if self.type != LLMResponseFormatType.JSON_SCHEMA and self.json_schema is not None:
            raise ValueError("json_schema can only be set when type is json_schema.")
        return self


class LLMMessage(BaseModel):
    role: LLMMessageRole
    content: str
    name: str | None = None


class LLMRequestOptions(BaseModel):
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] = Field(default_factory=list)
    seed: int | None = None
    response_format: LLMResponseFormat = Field(default_factory=LLMResponseFormat)


class LLMRequest(BaseModel):
    """Canonical request shape shared by all future LLM-backed backend features."""

    task_name: str = "default"
    messages: list[LLMMessage]
    model: str | None = None
    options: LLMRequestOptions = Field(default_factory=LLMRequestOptions)


class LLMUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMResponse(BaseModel):
    provider: LLMProviderName
    provider_request_id: str | None = None
    model: str
    finish_reason: str | None = None
    message: LLMMessage
    usage: LLMUsage | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
