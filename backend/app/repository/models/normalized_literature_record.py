from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class NormalizedLiteratureRecordModel(Base):
    __tablename__ = "normalized_literature_records"
    __table_args__ = (
        UniqueConstraint(
            "fetch_run_id",
            "literature_key",
            name="uq_normalized_literature_records_fetch_run_literature_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    fetch_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fetch_runs.id", ondelete="CASCADE"),
        index=True,
    )
    literature_key: Mapped[str] = mapped_column(String(255), index=True)
    pmid: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
