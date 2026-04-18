from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_report_generation_service
from app.infra.exceptions import AppException
from app.main import app
from tests.report_testkit import build_sample_report


class StubReportGenerationService:
    def build(self, fetch_run_id: str):
        assert fetch_run_id == "fetch-run-1"
        return build_sample_report(fetch_run_id)

    def get_report(self, fetch_run_id: str):
        assert fetch_run_id == "fetch-run-1"
        return build_sample_report(fetch_run_id)

    def list_sources(self, fetch_run_id: str):
        assert fetch_run_id == "fetch-run-1"
        return build_sample_report(fetch_run_id).source_refs


class MissingAnalysisStubReportGenerationService:
    def build(self, fetch_run_id: str):
        raise AppException(
            "Analysis snapshot is required before generating a report.",
            code="analysis_snapshot_required",
            status_code=409,
            details={"fetch_run_id": fetch_run_id},
        )

    def get_report(self, fetch_run_id: str):
        raise AssertionError("Should not be called in this test.")

    def list_sources(self, fetch_run_id: str):
        raise AssertionError("Should not be called in this test.")


def test_build_report_endpoint_returns_report_payload() -> None:
    app.dependency_overrides[get_report_generation_service] = (
        lambda: StubReportGenerationService()
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/fetches/fetch-run-1/report")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["fetch_run_id"] == "fetch-run-1"
    assert payload["target"] == "HER2"
    assert payload["sections"][0]["section_name"] == "target_overview"
    assert payload["warning_summary"][0]["code"] == "report_context_reference_missing"


def test_get_report_endpoint_returns_latest_report() -> None:
    app.dependency_overrides[get_report_generation_service] = (
        lambda: StubReportGenerationService()
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/fetches/fetch-run-1/report")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_id"] == "report-1"
    assert payload["markdown_content"].startswith("# HER2 医疗情报报告")


def test_list_report_sources_endpoint_returns_flat_source_list() -> None:
    app.dependency_overrides[get_report_generation_service] = (
        lambda: StubReportGenerationService()
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/fetches/fetch-run-1/report/sources")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["fetch_run_id"] == "fetch-run-1"
    assert payload["report_id"] == "report-1"
    assert payload["total_items"] == 1
    assert payload["items"][0]["section_name"] == "target_overview"
    assert payload["items"][0]["record_key"] == "12345678"


def test_build_report_endpoint_returns_409_when_analysis_snapshot_missing() -> None:
    app.dependency_overrides[get_report_generation_service] = (
        lambda: MissingAnalysisStubReportGenerationService()
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/fetches/fetch-run-1/report")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "analysis_snapshot_required"
