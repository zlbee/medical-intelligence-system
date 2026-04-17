from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class FetchRunModel(Base):
    __tablename__ = "fetch_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    target: Mapped[str] = mapped_column(String(255), index=True)
    indication: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_configs: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    raw_record_count: Mapped[int] = mapped_column(Integer, default=0)
    source_results: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

