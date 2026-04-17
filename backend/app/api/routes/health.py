from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings
from app.api.schemas.health import ComponentStatus, HealthResponse
from app.infra.db import check_database_connection
from app.infra.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    database_ok = check_database_connection()
    overall_status = "ok" if database_ok else "degraded"

    return HealthResponse(
        service=settings.app_name,
        environment=settings.app_env,
        version=settings.app_version,
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        database=ComponentStatus(
            status="ok" if database_ok else "degraded",
            detail=settings.database_url,
        ),
    )

