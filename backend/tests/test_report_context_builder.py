from __future__ import annotations

from sqlalchemy import delete

from app.domain import AnalysisDimensionName
from app.infra.db import SessionLocal, initialize_database
from app.infra.exceptions import AppException
from app.report import ReportContextBuilder
from app.repository import (
    AnalysisSnapshotRepository,
    LiteratureLLMEnrichmentRepository,
    TrialLLMEnrichmentRepository,
)
from app.repository.models import TrialLLMEnrichmentModel
from tests.report_testkit import clear_all_tables, seed_stage_two_artifacts


def test_report_context_builder_joins_snapshot_and_enrichments() -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, bundle = seed_stage_two_artifacts(session)

    builder = ReportContextBuilder(
        analysis_snapshot_repository=AnalysisSnapshotRepository(session),
        trial_llm_enrichment_repository=TrialLLMEnrichmentRepository(session),
        literature_llm_enrichment_repository=LiteratureLLMEnrichmentRepository(session),
    )

    built_bundle, contexts, warnings = builder.build(fetch_run_id)

    target_context = contexts[AnalysisDimensionName.TARGET_OVERVIEW]
    assert built_bundle.bundle_id == bundle.bundle_id
    assert not warnings
    assert target_context.title == "靶点概述"
    assert [item.trial_key for item in target_context.trials] == ["NCT03188393"]
    assert [item.literature_key for item in target_context.literature] == ["12345678"]
    assert [item.trial_key for item in target_context.trial_enrichments] == ["NCT03188393"]
    assert target_context.global_stats["top_mesh_terms"][0]["name"] == "Breast Neoplasms"

    session.close()


def test_report_context_builder_warns_when_selected_enrichment_is_missing() -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, _ = seed_stage_two_artifacts(session)
    session.execute(delete(TrialLLMEnrichmentModel))
    session.commit()

    builder = ReportContextBuilder(
        analysis_snapshot_repository=AnalysisSnapshotRepository(session),
        trial_llm_enrichment_repository=TrialLLMEnrichmentRepository(session),
        literature_llm_enrichment_repository=LiteratureLLMEnrichmentRepository(session),
    )

    _, contexts, warnings = builder.build(fetch_run_id)

    pipeline_context = contexts[AnalysisDimensionName.PIPELINE_OVERVIEW]
    assert [item.trial_key for item in pipeline_context.trials] == ["NCT03188393"]
    assert pipeline_context.trial_enrichments == []
    assert any(item.code == "report_context_reference_missing" for item in warnings)
    assert any("no persisted LLM enrichment" in item for item in pipeline_context.warnings)

    session.close()


def test_report_context_builder_requires_analysis_snapshot() -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    builder = ReportContextBuilder(
        analysis_snapshot_repository=AnalysisSnapshotRepository(session),
        trial_llm_enrichment_repository=TrialLLMEnrichmentRepository(session),
        literature_llm_enrichment_repository=LiteratureLLMEnrichmentRepository(session),
    )

    try:
        builder.build("missing-fetch-run")
        raise AssertionError("Expected analysis snapshot requirement error.")
    except AppException as exc:
        assert exc.status_code == 409
        assert exc.code == "analysis_snapshot_required"
    finally:
        session.close()
