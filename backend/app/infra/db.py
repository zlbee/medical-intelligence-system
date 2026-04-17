from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.infra.settings import get_settings


class Base(DeclarativeBase):
    """Base declarative model."""


settings = get_settings()


def _build_connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _ensure_sqlite_directory(url: URL) -> None:
    if not url.drivername.startswith("sqlite") or not url.database:
        return
    if url.database == ":memory:":
        return

    database_path = Path(url.database).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)


engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    connect_args=_build_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def initialize_database() -> None:
    url = make_url(settings.database_url)
    _ensure_sqlite_directory(url)
    Base.metadata.create_all(bind=engine)


def check_database_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

