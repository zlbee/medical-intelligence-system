from __future__ import annotations

from typing import Any

from app.infra.exceptions import AppException


class LLMError(AppException):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=status_code,
            details=details,
        )


class LLMConfigurationError(LLMError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="llm_configuration_error",
            status_code=503,
            details=details,
        )


class LLMProviderRequestError(LLMError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="llm_provider_request_failed",
            status_code=502,
            details=details,
        )


class LLMResponseParseError(LLMError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="llm_response_parse_error",
            status_code=502,
            details=details,
        )

