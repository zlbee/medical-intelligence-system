from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import get_fetch_pipeline_service
from app.domain import RawRecord, SourceName
from app.main import app


class StubFetchPipelineService:
    def list_raw_records(
        self,
        fetch_run_id: str,
        *,
        source_name: SourceName | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RawRecord]:
        assert fetch_run_id == "fetch-run-1"
        assert source_name is None
        assert limit == 50
        assert offset == 0
        return [
            RawRecord(
                record_id="record-1",
                fetch_run_id=fetch_run_id,
                source_name=SourceName.CLINICALTRIALS,
                source_id="NCT00000001",
                source_url="https://example.com/study/NCT00000001",
                target="HER2",
                indication="breast cancer",
                payload={"very": "large raw payload"},
                query_snapshot={"term": "HER2"},
                retrieved_at=datetime(2026, 4, 17, tzinfo=timezone.utc),
            )
        ]


def test_list_raw_records_endpoint_omits_payload_from_response() -> None:
    # The backend still keeps raw payloads internally, but the list endpoint
    # should return a slimmed-down record to avoid sending large blobs to UI.
    app.dependency_overrides[get_fetch_pipeline_service] = (
        lambda: StubFetchPipelineService()
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/fetches/fetch-run-1/records")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["fetch_run_id"] == "fetch-run-1"
    assert payload["total_items"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["source_id"] == "NCT00000001"
    assert payload["items"][0]["query_snapshot"] == {"term": "HER2"}
    assert "payload" not in payload["items"][0]
