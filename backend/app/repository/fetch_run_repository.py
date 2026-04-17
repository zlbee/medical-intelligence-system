from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import FetchRun, SourceFetchSummary, TargetQuery
from app.repository.models import FetchRunModel


class FetchRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, query: TargetQuery) -> FetchRun:
        model = FetchRunModel(
            target=query.target,
            indication=query.indication,
            aliases=query.aliases,
            source_configs=query.source_configs.model_dump(mode="json"),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return self._to_domain(model)

    def update_summary(
        self,
        fetch_run_id: str,
        *,
        status: str,
        raw_record_count: int,
        source_results: list[SourceFetchSummary],
        warnings: list[str],
    ) -> FetchRun:
        model = self.get_model(fetch_run_id)
        model.status = status
        model.raw_record_count = raw_record_count
        model.source_results = [item.model_dump(mode="json") for item in source_results]
        model.warnings = warnings
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return self._to_domain(model)

    def get(self, fetch_run_id: str) -> FetchRun | None:
        model = self.get_model(fetch_run_id, required=False)
        if model is None:
            return None
        return self._to_domain(model)

    def get_model(self, fetch_run_id: str, *, required: bool = True) -> FetchRunModel | None:
        statement = select(FetchRunModel).where(FetchRunModel.id == fetch_run_id)
        model = self.session.scalar(statement)
        if model is None and required:
            return None
        return model

    def _to_domain(self, model: FetchRunModel) -> FetchRun:
        return FetchRun(
            fetch_run_id=model.id,
            target=model.target,
            indication=model.indication,
            aliases=list(model.aliases or []),
            source_configs=dict(model.source_configs or {}),
            status=model.status,
            raw_record_count=model.raw_record_count,
            source_results=[
                SourceFetchSummary.model_validate(item)
                for item in (model.source_results or [])
            ],
            warnings=list(model.warnings or []),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

