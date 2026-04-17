from __future__ import annotations

from abc import ABC, abstractmethod

from app.llm.models import LLMProviderName, LLMRequest, LLMResponse


class BaseLLMProvider(ABC):
    provider_name: LLMProviderName

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Executes one model request and returns a normalized response."""

