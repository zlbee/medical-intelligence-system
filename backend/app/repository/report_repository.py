from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain import ReportDocument
from app.repository.models import ReportModel


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_fetch_run(
        self,
        report: ReportDocument,
    ) -> ReportDocument:
        self.session.execute(delete(ReportModel).where(ReportModel.fetch_run_id == report.fetch_run_id))
        self.session.add(
            ReportModel(
                id=report.report_id,
                fetch_run_id=report.fetch_run_id,
                analysis_bundle_id=report.analysis_bundle_id,
                target=report.target,
                payload=report.model_dump(mode="json"),
                generated_at=report.generated_at,
            )
        )
        self.session.commit()
        return self.get_by_fetch_run(report.fetch_run_id)  # type: ignore[return-value]

    def get_by_fetch_run(self, fetch_run_id: str) -> ReportDocument | None:
        statement = select(ReportModel).where(ReportModel.fetch_run_id == fetch_run_id)
        model = self.session.scalar(statement)
        if model is None:
            return None
        return ReportDocument.model_validate(model.payload)
