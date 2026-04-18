from __future__ import annotations

from app.infra.db import SessionLocal, initialize_database
from app.repository import (
    FetchRunRepository,
    LiteratureLLMEnrichmentRepository,
    NormalizedLiteratureRecordRepository,
    NormalizedTrialRecordRepository,
    TrialLLMEnrichmentRepository,
)
from tests.report_testkit import (
    build_sample_literature,
    build_sample_literature_enrichment,
    build_sample_trial,
    build_sample_trial_enrichment,
    clear_all_tables,
)


def test_normalized_record_repositories_find_latest_records_by_business_key() -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_repository = FetchRunRepository(session)
    first_fetch_run = fetch_run_repository.create(_build_query())
    second_fetch_run = fetch_run_repository.create(_build_query())

    trial_repository = NormalizedTrialRecordRepository(session)
    first_trial = build_sample_trial().model_copy(deep=True)
    first_trial.brief_title = "Original HER2 Trial"
    _set_trial_fetch_context(first_trial, first_fetch_run.fetch_run_id)
    second_trial = build_sample_trial().model_copy(deep=True)
    second_trial.brief_title = "Updated HER2 Trial"
    _set_trial_fetch_context(second_trial, second_fetch_run.fetch_run_id)
    trial_repository.replace_for_fetch_run(first_fetch_run.fetch_run_id, [first_trial])
    trial_repository.replace_for_fetch_run(second_fetch_run.fetch_run_id, [second_trial])

    literature_repository = NormalizedLiteratureRecordRepository(session)
    first_literature = build_sample_literature().model_copy(deep=True)
    first_literature.title = "Original HER2 Paper"
    _set_literature_fetch_context(first_literature, first_fetch_run.fetch_run_id)
    second_literature = build_sample_literature().model_copy(deep=True)
    second_literature.title = "Updated HER2 Paper"
    _set_literature_fetch_context(second_literature, second_fetch_run.fetch_run_id)
    literature_repository.replace_for_fetch_run(
        first_fetch_run.fetch_run_id,
        [first_literature],
    )
    literature_repository.replace_for_fetch_run(
        second_fetch_run.fetch_run_id,
        [second_literature],
    )

    latest_trials = trial_repository.find_latest_by_trial_keys(["NCT03188393", "missing"])
    latest_literature = literature_repository.find_latest_by_literature_keys(
        ["12345678", "missing"]
    )

    assert latest_trials["NCT03188393"].brief_title == "Updated HER2 Trial"
    assert latest_literature["12345678"].title == "Updated HER2 Paper"
    assert "missing" not in latest_trials
    assert "missing" not in latest_literature

    session.close()


def test_llm_enrichment_repositories_find_latest_records_by_business_key() -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_repository = FetchRunRepository(session)
    first_fetch_run = fetch_run_repository.create(_build_query())
    second_fetch_run = fetch_run_repository.create(_build_query())

    trial_repository = TrialLLMEnrichmentRepository(session)
    first_trial_enrichment = build_sample_trial_enrichment(first_fetch_run.fetch_run_id)
    first_trial_enrichment.dimension_insights.pipeline_overview.summary = "Original trial enrichment"
    second_trial_enrichment = build_sample_trial_enrichment(second_fetch_run.fetch_run_id)
    second_trial_enrichment.dimension_insights.pipeline_overview.summary = "Updated trial enrichment"
    trial_repository.replace_for_fetch_run(
        first_fetch_run.fetch_run_id,
        [first_trial_enrichment],
    )
    trial_repository.replace_for_fetch_run(
        second_fetch_run.fetch_run_id,
        [second_trial_enrichment],
    )

    literature_repository = LiteratureLLMEnrichmentRepository(session)
    first_literature_enrichment = build_sample_literature_enrichment(
        first_fetch_run.fetch_run_id
    )
    first_literature_enrichment.dimension_insights.research_update.summary = (
        "Original literature enrichment"
    )
    second_literature_enrichment = build_sample_literature_enrichment(
        second_fetch_run.fetch_run_id
    )
    second_literature_enrichment.dimension_insights.research_update.summary = (
        "Updated literature enrichment"
    )
    literature_repository.replace_for_fetch_run(
        first_fetch_run.fetch_run_id,
        [first_literature_enrichment],
    )
    literature_repository.replace_for_fetch_run(
        second_fetch_run.fetch_run_id,
        [second_literature_enrichment],
    )

    latest_trials = trial_repository.find_latest_by_trial_keys(["NCT03188393", "missing"])
    latest_literature = literature_repository.find_latest_by_literature_keys(
        ["12345678", "missing"]
    )

    assert (
        latest_trials["NCT03188393"].dimension_insights.pipeline_overview.summary
        == "Updated trial enrichment"
    )
    assert (
        latest_literature["12345678"].dimension_insights.research_update.summary
        == "Updated literature enrichment"
    )
    assert "missing" not in latest_trials
    assert "missing" not in latest_literature

    session.close()


def _build_query():
    from app.domain import TargetQuery

    return TargetQuery(target="HER2", indication="breast cancer", aliases=["ERBB2"])


def _set_trial_fetch_context(trial, fetch_run_id: str) -> None:
    for trace in trial.source_traces:
        trace.fetch_run_id = fetch_run_id


def _set_literature_fetch_context(literature, fetch_run_id: str) -> None:
    for trace in literature.source_traces:
        trace.fetch_run_id = fetch_run_id
