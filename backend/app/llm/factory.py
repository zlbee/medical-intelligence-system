from __future__ import annotations

import httpx

from app.infra.settings import Settings, get_settings
from app.llm.client import LLMClient
from app.llm.errors import LLMConfigurationError
from app.llm.models import LLMProviderName
from app.llm.providers import OpenRouterProvider


def build_llm_client(
    settings: Settings | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> LLMClient:
    resolved_settings = settings or get_settings()

    try:
        provider_name = LLMProviderName(resolved_settings.llm_provider)
    except ValueError as exc:
        raise LLMConfigurationError(
            "Unsupported LLM provider configured.",
            details={"provider": resolved_settings.llm_provider},
        ) from exc

    if provider_name == LLMProviderName.OPENROUTER:
        return LLMClient(
            OpenRouterProvider(
                api_key=resolved_settings.llm_api_key,
                default_model=resolved_settings.llm_default_model,
                base_url=resolved_settings.llm_openrouter_base_url,
                timeout_seconds=resolved_settings.llm_request_timeout_seconds,
                app_url=resolved_settings.llm_openrouter_site_url,
                app_title=resolved_settings.llm_openrouter_app_title,
                enable_response_healing=resolved_settings.llm_enable_response_healing,
                http_client=http_client,
            )
        )

    raise LLMConfigurationError(
        "LLM provider is not implemented yet.",
        details={"provider": provider_name.value},
    )

