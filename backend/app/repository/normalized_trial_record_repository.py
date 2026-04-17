from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain import NormalizedTrialRecord
from app.repository.models import NormalizedTrialRecordModel


class NormalizedTrialRecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_fetch_run(
        self,
        fetch_run_id: str,
        records: list[NormalizedTrialRecord],
    ) -> list[NormalizedTrialRecord]:
        self.session.execute(
            delete(NormalizedTrialRecordModel).where(
                NormalizedTrialRecordModel.fetch_run_id == fetch_run_id
            )
        )
        self.session.add_all(
            [
                NormalizedTrialRecordModel(
                    fetch_run_id=fetch_run_id,
                    trial_key=record.trial_key,
                    nct_id=record.nct_id,
                    payload=record.model_dump(mode="json"),
                )
                for record in records
            ]
        )
        self.session.commit()
        return self.list_by_fetch_run(fetch_run_id)

    def list_by_fetch_run(self, fetch_run_id: str) -> list[NormalizedTrialRecord]:
        statement = (
            select(NormalizedTrialRecordModel)
            .where(NormalizedTrialRecordModel.fetch_run_id == fetch_run_id)
            .order_by(NormalizedTrialRecordModel.created_at.asc())
        )
        models = self.session.scalars(statement).all()
        return [
            NormalizedTrialRecord.model_validate(model.payload)
            for model in models
        ]
