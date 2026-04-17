from collections.abc import Generator

from sqlalchemy.orm import Session

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

