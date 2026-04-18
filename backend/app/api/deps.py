from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.orchestration import AnalysisPipelineService
from app.orchestration import FetchPipelineService
from app.infra.db import SessionLocal
from app.infra.settings import Settings, get_settings
from app.llm import LLMClient, LLMError, build_llm_client


def get_app_settings() -> Settings:
    return get_settings()


@lru_cache
def _get_cached_llm_client() -> LLMClient:
    return build_llm_client(get_settings())


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


def get_analysis_pipeline_service(
    session: Session = Depends(get_db_session),
) -> AnalysisPipelineService:
    settings = get_settings()
    llm_client: LLMClient | None = None
    try:
        llm_client = build_llm_client(settings)
    except LLMError:
        # Analysis can still run with deterministic scoring only when LLM configuration
        # is absent or temporarily unavailable.
        llm_client = None
    return AnalysisPipelineService(
        session,
        llm_client=llm_client,
        llm_model=settings.llm_default_model,
    )


def get_llm_client() -> LLMClient:
    return _get_cached_llm_client()
