from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domain import RawRecord, SourceName
from app.repository.models import FetchRunRawRecordModel, RawRecordModel


class RawRecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_many(self, records: list[RawRecord]) -> None:
        if not records:
            return

        unique_records = self._dedupe_incoming_records(records)
        existing_models = self._load_existing_raw_records(unique_records)
        links_to_add: list[FetchRunRawRecordModel] = []
        seen_links = self._load_existing_link_keys(unique_records, existing_models)

        for record in unique_records:
            dedupe_key = self._dedupe_key(record.source_name.value, record.source_id)
            raw_record_model = existing_models.get(dedupe_key)

            if raw_record_model is None:
                raw_record_model = RawRecordModel(
                    id=record.record_id,
                    fetch_run_id=record.fetch_run_id,
                    source_name=record.source_name.value,
                    source_id=record.source_id,
                    source_url=record.source_url,
                    target=record.target,
                    indication=record.indication,
                    payload=record.payload,
                    query_snapshot=record.query_snapshot,
                    retrieved_at=record.retrieved_at,
                    created_at=record.retrieved_at,
                )
                self.session.add(raw_record_model)
                existing_models[dedupe_key] = raw_record_model
            else:
                raw_record_model.source_url = record.source_url
                raw_record_model.payload = record.payload

            link_key = (record.fetch_run_id, raw_record_model.id)
            if link_key in seen_links:
                continue
            seen_links.add(link_key)
            links_to_add.append(
                FetchRunRawRecordModel(
                    fetch_run_id=record.fetch_run_id,
                    raw_record_id=raw_record_model.id,
                    target=record.target,
                    indication=record.indication,
                    query_snapshot=record.query_snapshot,
                    retrieved_at=record.retrieved_at,
                    created_at=record.retrieved_at,
                )
            )
        self.session.add_all(links_to_add)
        self.session.commit()

    def list_by_fetch_run(
        self,
        fetch_run_id: str,
        *,
        source_name: SourceName | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RawRecord]:
        statement = (
            select(FetchRunRawRecordModel, RawRecordModel)
            .join(
                RawRecordModel,
                RawRecordModel.id == FetchRunRawRecordModel.raw_record_id,
            )
            .where(FetchRunRawRecordModel.fetch_run_id == fetch_run_id)
            .order_by(FetchRunRawRecordModel.retrieved_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if source_name is not None:
            statement = statement.where(RawRecordModel.source_name == source_name.value)

        rows = self.session.execute(statement).all()
        return [
            self._to_domain(link_model, raw_record_model)
            for link_model, raw_record_model in rows
        ]

    def list_all_by_fetch_run(
        self,
        fetch_run_id: str,
        *,
        source_name: SourceName | None = None,
    ) -> list[RawRecord]:
        statement = (
            select(FetchRunRawRecordModel, RawRecordModel)
            .join(
                RawRecordModel,
                RawRecordModel.id == FetchRunRawRecordModel.raw_record_id,
            )
            .where(FetchRunRawRecordModel.fetch_run_id == fetch_run_id)
            .order_by(FetchRunRawRecordModel.retrieved_at.desc())
        )
        if source_name is not None:
            statement = statement.where(RawRecordModel.source_name == source_name.value)

        rows = self.session.execute(statement).all()
        return [
            self._to_domain(link_model, raw_record_model)
            for link_model, raw_record_model in rows
        ]

    def _to_domain(
        self,
        link_model: FetchRunRawRecordModel,
        raw_record_model: RawRecordModel,
    ) -> RawRecord:
        return RawRecord(
            record_id=raw_record_model.id,
            fetch_run_id=link_model.fetch_run_id,
            source_name=raw_record_model.source_name,
            source_id=raw_record_model.source_id,
            source_url=raw_record_model.source_url,
            target=link_model.target,
            indication=link_model.indication,
            payload=raw_record_model.payload,
            query_snapshot=link_model.query_snapshot,
            retrieved_at=link_model.retrieved_at,
        )

    def _load_existing_raw_records(
        self,
        records: list[RawRecord],
    ) -> dict[tuple[str, str], RawRecordModel]:
        if not records:
            return {}

        conditions = [
            and_(
                RawRecordModel.source_name == record.source_name.value,
                RawRecordModel.source_id == record.source_id,
            )
            for record in records
        ]
        statement = select(RawRecordModel).where(or_(*conditions))
        models = self.session.scalars(statement).all()
        return {
            self._dedupe_key(model.source_name, model.source_id): model
            for model in models
        }

    def _dedupe_incoming_records(self, records: list[RawRecord]) -> list[RawRecord]:
        deduped: dict[tuple[str, str], RawRecord] = {}
        for record in records:
            deduped[self._dedupe_key(record.source_name.value, record.source_id)] = record
        return list(deduped.values())

    def _dedupe_key(self, source_name: str, source_id: str) -> tuple[str, str]:
        return source_name, source_id

    def _load_existing_link_keys(
        self,
        records: list[RawRecord],
        existing_models: dict[tuple[str, str], RawRecordModel],
    ) -> set[tuple[str, str]]:
        if not records:
            return set()

        conditions = []
        for record in records:
            raw_record_model = existing_models.get(
                self._dedupe_key(record.source_name.value, record.source_id)
            )
            if raw_record_model is None:
                continue
            conditions.append(
                and_(
                    FetchRunRawRecordModel.fetch_run_id == record.fetch_run_id,
                    FetchRunRawRecordModel.raw_record_id == raw_record_model.id,
                )
            )

        if not conditions:
            return set()

        statement = select(
            FetchRunRawRecordModel.fetch_run_id,
            FetchRunRawRecordModel.raw_record_id,
        ).where(or_(*conditions))
        rows = self.session.execute(statement).all()
        return {(fetch_run_id, raw_record_id) for fetch_run_id, raw_record_id in rows}
