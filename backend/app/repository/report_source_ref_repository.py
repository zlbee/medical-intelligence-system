from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain import AnalysisDimensionName, ReportSourceRef
from app.repository.models import ReportSourceRefModel

SECTION_SORT_ORDER = {
    AnalysisDimensionName.TARGET_OVERVIEW: 0,
    AnalysisDimensionName.PIPELINE_OVERVIEW: 1,
    AnalysisDimensionName.RESEARCH_UPDATE: 2,
    AnalysisDimensionName.COMPETITION_ASSESSMENT: 3,
}


class ReportSourceRefRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_fetch_run(
        self,
        *,
        fetch_run_id: str,
        refs: list[ReportSourceRef],
    ) -> list[ReportSourceRef]:
        self.session.execute(
            delete(ReportSourceRefModel).where(ReportSourceRefModel.fetch_run_id == fetch_run_id)
        )
        self.session.add_all(
            [
                ReportSourceRefModel(
                    report_id=ref.report_id,
                    fetch_run_id=ref.fetch_run_id,
                    section_name=ref.section_name.value,
                    source_type=ref.source_type.value,
                    record_key=ref.record_key,
                    source_id=ref.source_id,
                    display_title=ref.display_title,
                    source_url=ref.source_url,
                    display_order=ref.display_order,
                    payload=ref.model_dump(mode="json"),
                )
                for ref in refs
            ]
        )
        self.session.commit()
        return self.list_by_fetch_run(fetch_run_id)

    def list_by_fetch_run(self, fetch_run_id: str) -> list[ReportSourceRef]:
        statement = select(ReportSourceRefModel).where(
            ReportSourceRefModel.fetch_run_id == fetch_run_id
        )
        models = self.session.scalars(statement).all()
        refs = [ReportSourceRef.model_validate(model.payload) for model in models]
        refs.sort(
            key=lambda item: (
                SECTION_SORT_ORDER.get(item.section_name, 99),
                item.display_order,
                item.record_key,
            )
        )
        return refs
