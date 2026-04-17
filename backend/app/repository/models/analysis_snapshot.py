from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base


class AnalysisSnapshotModel(Base):
    __tablename__ = "analysis_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "fetch_run_id",
            name="uq_analysis_snapshots_fetch_run",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fetch_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fetch_runs.id", ondelete="CASCADE"),
        index=True,
    )
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
