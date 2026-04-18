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

    def find_latest_by_trial_keys(
        self,
        trial_keys: list[str],
    ) -> dict[str, NormalizedTrialRecord]:
        if not trial_keys:
            return {}
        statement = (
            select(NormalizedTrialRecordModel)
            .where(NormalizedTrialRecordModel.trial_key.in_(trial_keys))
            .order_by(
                NormalizedTrialRecordModel.trial_key.asc(),
                NormalizedTrialRecordModel.created_at.desc(),
                NormalizedTrialRecordModel.id.desc(),
            )
        )
        models = self.session.scalars(statement).all()
        latest_by_key: dict[str, NormalizedTrialRecord] = {}
        for model in models:
            if model.trial_key in latest_by_key:
                continue
            latest_by_key[model.trial_key] = NormalizedTrialRecord.model_validate(model.payload)
        return latest_by_key
