from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain import NormalizedLiteratureRecord
from app.repository.models import NormalizedLiteratureRecordModel


class NormalizedLiteratureRecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_fetch_run(
        self,
        fetch_run_id: str,
        records: list[NormalizedLiteratureRecord],
    ) -> list[NormalizedLiteratureRecord]:
        self.session.execute(
            delete(NormalizedLiteratureRecordModel).where(
                NormalizedLiteratureRecordModel.fetch_run_id == fetch_run_id
            )
        )
        self.session.add_all(
            [
                NormalizedLiteratureRecordModel(
                    fetch_run_id=fetch_run_id,
                    literature_key=record.literature_key,
                    pmid=record.pmid,
                    doi=record.doi,
                    payload=record.model_dump(mode="json"),
                )
                for record in records
            ]
        )
        self.session.commit()
        return self.list_by_fetch_run(fetch_run_id)

    def list_by_fetch_run(self, fetch_run_id: str) -> list[NormalizedLiteratureRecord]:
        statement = (
            select(NormalizedLiteratureRecordModel)
            .where(NormalizedLiteratureRecordModel.fetch_run_id == fetch_run_id)
            .order_by(NormalizedLiteratureRecordModel.created_at.asc())
        )
        models = self.session.scalars(statement).all()
        return [
            NormalizedLiteratureRecord.model_validate(model.payload)
            for model in models
        ]
