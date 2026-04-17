from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import AnalysisReadyBundle
from app.repository.models import AnalysisSnapshotModel


class AnalysisSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        fetch_run_id: str,
        bundle: AnalysisReadyBundle,
    ) -> AnalysisReadyBundle:
        model = self.get_model(fetch_run_id)
        payload = bundle.model_dump(mode="json")
        if model is None:
            model = AnalysisSnapshotModel(
                id=bundle.bundle_id,
                fetch_run_id=fetch_run_id,
                payload=payload,
            )
        else:
            model.id = bundle.bundle_id
            model.payload = payload
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return AnalysisReadyBundle.model_validate(model.payload)

    def get(self, fetch_run_id: str) -> AnalysisReadyBundle | None:
        model = self.get_model(fetch_run_id)
        if model is None:
            return None
        return AnalysisReadyBundle.model_validate(model.payload)

    def get_model(self, fetch_run_id: str) -> AnalysisSnapshotModel | None:
        statement = select(AnalysisSnapshotModel).where(
            AnalysisSnapshotModel.fetch_run_id == fetch_run_id
        )
        return self.session.scalar(statement)
