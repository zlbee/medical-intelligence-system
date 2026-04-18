from __future__ import annotations

from sqlalchemy import delete

from app.domain import (
    FinalScoreBreakdown,
    LLMScoreBreakdown,
    LiteratureLLMEnrichment,
    RuleScoreBreakdown,
    TargetQuery,
    TrialLLMEnrichment,
)
from app.infra.db import SessionLocal, initialize_database
from app.repository import (
    FetchRunRepository,
    LiteratureLLMEnrichmentRepository,
    TrialLLMEnrichmentRepository,
)
from app.repository.models import (
    FetchRunModel,
    LiteratureLLMEnrichmentModel,
    TrialLLMEnrichmentModel,
)


def test_llm_enrichment_repositories_replace_records_for_each_fetch_run() -> None:
    initialize_database()
    session = SessionLocal()
    session.execute(delete(LiteratureLLMEnrichmentModel))
    session.execute(delete(TrialLLMEnrichmentModel))
    session.execute(delete(FetchRunModel))
    session.commit()

    fetch_run = FetchRunRepository(session).create(TargetQuery(target="HER2"))
    trial_repository = TrialLLMEnrichmentRepository(session)
    literature_repository = LiteratureLLMEnrichmentRepository(session)

    trial_repository.replace_for_fetch_run(
        fetch_run.fetch_run_id,
        [
            TrialLLMEnrichment(
                fetch_run_id=fetch_run.fetch_run_id,
                trial_key="trial-1",
                nct_id="NCT1",
                rule_scores=RuleScoreBreakdown(pipeline_overview=10),
                llm_scores=LLMScoreBreakdown(pipeline_overview=80),
                final_scores=FinalScoreBreakdown(pipeline_overview=34),
                prompt_version="trial_enrichment_v1",
            )
        ],
    )
    literature_repository.replace_for_fetch_run(
        fetch_run.fetch_run_id,
        [
            LiteratureLLMEnrichment(
                fetch_run_id=fetch_run.fetch_run_id,
                literature_key="paper-1",
                pmid="123",
                rule_scores=RuleScoreBreakdown(research_update=20),
                llm_scores=LLMScoreBreakdown(research_update=90),
                final_scores=FinalScoreBreakdown(research_update=44.5),
                prompt_version="literature_enrichment_v1",
            )
        ],
    )

    trial_repository.replace_for_fetch_run(
        fetch_run.fetch_run_id,
        [
            TrialLLMEnrichment(
                fetch_run_id=fetch_run.fetch_run_id,
                trial_key="trial-2",
                nct_id="NCT2",
                rule_scores=RuleScoreBreakdown(pipeline_overview=50),
                llm_scores=LLMScoreBreakdown(pipeline_overview=55),
                final_scores=FinalScoreBreakdown(pipeline_overview=51.75),
                prompt_version="trial_enrichment_v1",
            )
        ],
    )

    trial_records = trial_repository.list_by_fetch_run(fetch_run.fetch_run_id)
    literature_records = literature_repository.list_by_fetch_run(fetch_run.fetch_run_id)

    assert [record.trial_key for record in trial_records] == ["trial-2"]
    assert [record.literature_key for record in literature_records] == ["paper-1"]

    session.close()
