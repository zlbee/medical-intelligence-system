from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import get_analysis_pipeline_service
from app.domain import (
    AnalysisReadyBundle,
    GlobalAnalysisStats,
    LLMEnrichmentSummary,
    NamedCount,
    TargetOverviewFacts,
    TargetQuery,
    WarningItem,
    WarningLevel,
    WarningScope,
)
from app.main import app


class StubAnalysisPipelineService:
    def build(self, fetch_run_id: str) -> AnalysisReadyBundle:
        assert fetch_run_id == "fetch-run-1"
        return _build_bundle()

    def get_bundle(self, fetch_run_id: str) -> AnalysisReadyBundle:
        assert fetch_run_id == "fetch-run-1"
        return _build_bundle()


def test_build_analysis_endpoint_returns_summary_payload() -> None:
    app.dependency_overrides[get_analysis_pipeline_service] = (
        lambda: StubAnalysisPipelineService()
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/fetches/fetch-run-1/analysis")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["fetch_run_id"] == "fetch-run-1"
    assert payload["global_stats"]["total_trial_count"] == 2
    assert payload["section_inputs"]["target_overview"]["facts"]["alias_terms"] == [
        "HER2",
        "ERBB2",
    ]
    assert payload["llm_enrichment_summary"]["trial_total"] == 2
    assert payload["warnings"][0]["code"] == "bundle_incomplete_coverage"
    assert "trials" not in payload
    assert "literature" not in payload
    assert "trial_llm_enrichments" not in payload


def test_get_analysis_endpoint_returns_latest_snapshot() -> None:
    app.dependency_overrides[get_analysis_pipeline_service] = (
        lambda: StubAnalysisPipelineService()
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/fetches/fetch-run-1/analysis")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["bundle_id"] == "bundle-1"
    assert payload["query"]["target"] == "HER2"
    assert payload["section_inputs"]["pipeline_overview"]["trial_keys"] == [
        "NCT00000001"
    ]


def _build_bundle() -> AnalysisReadyBundle:
    bundle = AnalysisReadyBundle(
        bundle_id="bundle-1",
        query=TargetQuery(target="HER2", indication="breast cancer", aliases=["ERBB2"]),
        global_stats=GlobalAnalysisStats(
            total_trial_count=2,
            total_literature_count=3,
            top_sponsors=[NamedCount(name="Example Sponsor", count=2)],
        ),
        llm_enrichment_summary=LLMEnrichmentSummary(
            trial_total=2,
            trial_succeeded=1,
            literature_total=3,
            literature_succeeded=2,
            warning_count=1,
            model="test-model",
            prompt_versions=["trial_enrichment_v1", "literature_enrichment_v1"],
        ),
    )
    bundle.section_inputs.target_overview.trial_keys = ["NCT00000001"]
    bundle.section_inputs.target_overview.literature_keys = ["12345678"]
    bundle.section_inputs.target_overview.facts = TargetOverviewFacts(
        alias_terms=["HER2", "ERBB2"],
        disease_contexts=["breast cancer"],
        representative_paper_keys=["12345678"],
    )
    bundle.section_inputs.pipeline_overview.trial_keys = ["NCT00000001"]
    bundle.section_inputs.pipeline_overview.facts.phase_distribution = {"PHASE2": 1}
    bundle.section_inputs.research_update.literature_keys = ["12345678"]
    bundle.section_inputs.research_update.facts.publication_count_by_year = {2025: 3}
    bundle.section_inputs.competition_assessment.facts.active_sponsor_count = 1
    bundle.coverage.has_trial_evidence = True
    bundle.coverage.has_literature_evidence = True
    bundle.coverage.has_target_overview_evidence = True
    bundle.coverage.has_pipeline_overview_evidence = True
    bundle.coverage.has_research_update_evidence = True
    bundle.coverage.has_competition_assessment_evidence = False
    bundle.coverage.missing_dimensions = ["competition_assessment"]
    bundle.coverage.notes = ["competition_assessment currently lacks enough selected evidence."]
    bundle.warnings = [
        WarningItem(
            code="bundle_incomplete_coverage",
            level=WarningLevel.WARNING,
            scope=WarningScope.BUNDLE,
            message="One or more report sections do not yet have enough selected evidence.",
            related_ids=["competition_assessment"],
            details={"missing_dimensions": ["competition_assessment"]},
        )
    ]
    bundle.built_at = datetime(2026, 4, 17, tzinfo=timezone.utc)
    return bundle
