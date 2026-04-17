import httpx

from app.infra.settings import Settings, get_settings


def build_http_client(settings: Settings | None = None) -> httpx.Client:
    resolved_settings = settings or get_settings()
    return httpx.Client(
        timeout=resolved_settings.external_request_timeout_seconds,
        headers={"User-Agent": resolved_settings.http_user_agent},
    )
