from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class RawRecordModel(Base):
    __tablename__ = "raw_records"
    __table_args__ = (
        UniqueConstraint("source_name", "source_id", name="uq_raw_records_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fetch_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fetch_runs.id", ondelete="CASCADE"),
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    indication: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    query_snapshot: Mapped[dict] = mapped_column(JSON)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
