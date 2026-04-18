from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain import LiteratureLLMEnrichment
from app.repository.models import LiteratureLLMEnrichmentModel


class LiteratureLLMEnrichmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_fetch_run(
        self,
        fetch_run_id: str,
        records: list[LiteratureLLMEnrichment],
    ) -> list[LiteratureLLMEnrichment]:
        self.session.execute(
            delete(LiteratureLLMEnrichmentModel).where(
                LiteratureLLMEnrichmentModel.fetch_run_id == fetch_run_id
            )
        )
        self.session.add_all(
            [
                LiteratureLLMEnrichmentModel(
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

    def list_by_fetch_run(self, fetch_run_id: str) -> list[LiteratureLLMEnrichment]:
        statement = (
            select(LiteratureLLMEnrichmentModel)
            .where(LiteratureLLMEnrichmentModel.fetch_run_id == fetch_run_id)
            .order_by(LiteratureLLMEnrichmentModel.created_at.asc())
        )
        models = self.session.scalars(statement).all()
        return [
            LiteratureLLMEnrichment.model_validate(model.payload) for model in models
        ]

    def find_latest_by_literature_keys(
        self,
        literature_keys: list[str],
    ) -> dict[str, LiteratureLLMEnrichment]:
        if not literature_keys:
            return {}
        statement = (
            select(LiteratureLLMEnrichmentModel)
            .where(LiteratureLLMEnrichmentModel.literature_key.in_(literature_keys))
            .order_by(
                LiteratureLLMEnrichmentModel.literature_key.asc(),
                LiteratureLLMEnrichmentModel.created_at.desc(),
                LiteratureLLMEnrichmentModel.id.desc(),
            )
        )
        models = self.session.scalars(statement).all()
        latest_by_key: dict[str, LiteratureLLMEnrichment] = {}
        for model in models:
            if model.literature_key in latest_by_key:
                continue
            latest_by_key[model.literature_key] = LiteratureLLMEnrichment.model_validate(
                model.payload
            )
        return latest_by_key
