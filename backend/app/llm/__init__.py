"""LLM base service abstractions shared by future enrichment and report flows."""

from app.llm.client import LLMClient
from app.llm.errors import (
    LLMConfigurationError,
    LLMError,
    LLMProviderRequestError,
    LLMResponseParseError,
)
from app.llm.factory import build_llm_client
from app.llm.models import (
    LLMJsonSchema,
    LLMMessage,
    LLMMessageRole,
    LLMProviderName,
    LLMRequest,
    LLMRequestOptions,
    LLMResponse,
    LLMResponseFormat,
    LLMResponseFormatType,
    LLMUsage,
)
from app.llm.providers import BaseLLMProvider, OpenRouterProvider

__all__ = [
    "BaseLLMProvider",
    "LLMClient",
    "LLMConfigurationError",
    "LLMError",
    "LLMJsonSchema",
    "LLMMessage",
    "LLMMessageRole",
    "LLMProviderName",
    "LLMProviderRequestError",
    "LLMRequest",
    "LLMRequestOptions",
    "LLMResponse",
    "LLMResponseFormat",
    "LLMResponseFormatType",
    "LLMResponseParseError",
    "LLMUsage",
    "OpenRouterProvider",
    "build_llm_client",
]

