from sqlalchemy import func, select
from datetime import datetime, timezone

from sqlalchemy import delete

from app.domain import ConnectorResult, RawRecord, SourceName, TargetQuery
from app.infra.db import SessionLocal, initialize_database
from app.orchestration import FetchPipelineService
from app.repository.models import FetchRunModel, FetchRunRawRecordModel, RawRecordModel


class SuccessfulConnector:
    source_name = SourceName.CLINICALTRIALS

    def search(self, query: TargetQuery, *, fetch_run_id: str) -> ConnectorResult:
        return ConnectorResult(
            source_name=self.source_name,
            raw_records=[
                RawRecord(
                    fetch_run_id=fetch_run_id,
                    source_name=self.source_name,
                    source_id="NCT00000001",
                    source_url="https://clinicaltrials.gov/study/NCT00000001",
                    target=query.target,
                    indication=query.indication,
                    payload={"title": "trial"},
                    query_snapshot={"source": "clinicaltrials"},
                    retrieved_at=datetime.now(timezone.utc),
                )
            ],
            total_count=1,
            elapsed_ms=10,
            request_snapshot={"source": "clinicaltrials"},
        )


class FailingConnector:
    source_name = SourceName.PUBMED

    def search(self, query: TargetQuery, *, fetch_run_id: str) -> ConnectorResult:
        raise RuntimeError("pubmed unavailable")


class DetailedConnector:
    source_name = SourceName.CLINICALTRIALS

    def search(self, query: TargetQuery, *, fetch_run_id: str) -> ConnectorResult:
        raw_records = [
            RawRecord(
                fetch_run_id=fetch_run_id,
                source_name=self.source_name,
                source_id=f"NCT{index:08d}",
                source_url=f"https://clinicaltrials.gov/study/NCT{index:08d}",
                target=query.target,
                indication=query.indication,
                payload={"title": f"trial-{index}"},
                query_snapshot={"page_index": index // 10},
                retrieved_at=datetime.now(timezone.utc),
            )
            for index in range(12)
        ]
        return ConnectorResult(
            source_name=self.source_name,
            raw_records=raw_records,
            total_count=50,
            elapsed_ms=25,
            request_snapshot={
                "applied_record_cap": 10,
                "stop_reason": "record_cap_reached",
                "pages": [{"page_index": 0}, {"page_index": 1}],
            },
        )


def test_fetch_pipeline_persists_successful_records_on_partial_failure() -> None:
    initialize_database()
    session = SessionLocal()
    session.execute(delete(FetchRunRawRecordModel))
    session.execute(delete(RawRecordModel))
    session.execute(delete(FetchRunModel))
    session.commit()

    service = FetchPipelineService(
        session,
        connectors=[SuccessfulConnector(), FailingConnector()],
    )
    query = TargetQuery(target="HER2")

    result = service.execute(query)
    records = service.list_raw_records(result.fetch_run_id)

    assert result.status.value == "partial_failure"
    assert result.raw_record_count == 1
    assert len(result.warnings) == 1
    assert len(records) == 1
    assert records[0].source_id == "NCT00000001"

    session.close()


def test_fetch_pipeline_deduplicates_raw_records_by_source_name_and_source_id() -> None:
    initialize_database()
    session = SessionLocal()
    session.execute(delete(FetchRunRawRecordModel))
    session.execute(delete(RawRecordModel))
    session.execute(delete(FetchRunModel))
    session.commit()

    service = FetchPipelineService(session, connectors=[SuccessfulConnector()])

    first_result = service.execute(TargetQuery(target="HER2"))
    second_result = service.execute(TargetQuery(target="HER2", aliases=["ERBB2"]))

    raw_record_count = session.scalar(select(func.count()).select_from(RawRecordModel))
    association_count = session.scalar(
        select(func.count()).select_from(FetchRunRawRecordModel)
    )

    first_records = service.list_raw_records(first_result.fetch_run_id)
    second_records = service.list_raw_records(second_result.fetch_run_id)

    assert first_result.raw_record_count == 1
    assert second_result.raw_record_count == 1
    assert raw_record_count == 1
    assert association_count == 2
    assert len(first_records) == 1
    assert len(second_records) == 1
    assert first_records[0].source_id == second_records[0].source_id == "NCT00000001"

    session.close()


def test_fetch_pipeline_preserves_request_snapshot_and_totals() -> None:
    initialize_database()
    session = SessionLocal()
    session.execute(delete(FetchRunRawRecordModel))
    session.execute(delete(RawRecordModel))
    session.execute(delete(FetchRunModel))
    session.commit()

    service = FetchPipelineService(session, connectors=[DetailedConnector()])

    result = service.execute(TargetQuery(target="HER2"))

    assert result.raw_record_count == 12
    assert len(result.source_results) == 1
    source_result = result.source_results[0]
    assert source_result.fetched_count == 12
    assert source_result.total_count == 50
    assert source_result.request_snapshot["applied_record_cap"] == 10
    assert source_result.request_snapshot["stop_reason"] == "record_cap_reached"
    assert len(source_result.request_snapshot["pages"]) == 2

    session.close()
