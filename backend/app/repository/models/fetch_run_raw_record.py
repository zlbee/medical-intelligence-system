from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class FetchRunRawRecordModel(Base):
    __tablename__ = "fetch_run_raw_records"
    __table_args__ = (
        PrimaryKeyConstraint(
            "fetch_run_id",
            "raw_record_id",
            name="pk_fetch_run_raw_record",
        ),
    )

    fetch_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fetch_runs.id", ondelete="CASCADE"),
        index=True,
    )
    raw_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("raw_records.id", ondelete="CASCADE"),
        index=True,
    )
    target: Mapped[str] = mapped_column(String(255), index=True)
    indication: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query_snapshot: Mapped[dict] = mapped_column(JSON)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
