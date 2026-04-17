from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.orchestration import FetchPipelineService
from app.infra.db import SessionLocal
from app.infra.settings import Settings, get_settings


def get_app_settings() -> Settings:
    return get_settings()


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_fetch_pipeline_service(
    session: Session = Depends(get_db_session),
) -> FetchPipelineService:
    return FetchPipelineService(session)
