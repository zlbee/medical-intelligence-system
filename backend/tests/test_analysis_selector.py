from __future__ import annotations

from app.analyze import AnalysisBundleBuilder, SectionSelector
from app.domain import (
    DimensionInsight,
    DimensionInsightBreakdown,
    FinalScoreBreakdown,
    LLMScoreBreakdown,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    RuleScoreBreakdown,
    TargetQuery,
    TrialLLMEnrichment,
)


def test_selector_prefers_final_scores_and_falls_back_to_rule_scores() -> None:
    selector = SectionSelector(pipeline_trial_limit=2)
    query = TargetQuery(target="HER2", indication="breast cancer")
    enriched_trial = NormalizedTrialRecord(
        trial_key="trial-enriched",
        brief_title="Exploratory study",
        conditions=["Solid Tumor"],
        phase="PHASE1",
        overall_status="ACTIVE_NOT_RECRUITING",
    )
    rule_only_trial = NormalizedTrialRecord(
        trial_key="trial-rule-only",
        brief_title="HER2 phase 3 breast cancer trial",
        conditions=["Breast Cancer"],
        phase="PHASE3",
        overall_status="RECRUITING",
    )
    low_value_trial = NormalizedTrialRecord(
        trial_key="trial-low",
        brief_title="Background registry",
        conditions=["Healthy Volunteers"],
        phase="EARLY_PHASE1",
        overall_status="COMPLETED",
    )

    selection = selector.select_pipeline_overview(
        query,
        [enriched_trial, rule_only_trial, low_value_trial],
        trial_enrichments_by_key={
            "trial-enriched": TrialLLMEnrichment(
                fetch_run_id="fetch-1",
                trial_key="trial-enriched",
                dimension_insights=DimensionInsightBreakdown(
                    pipeline_overview=DimensionInsight(can_contribute=True, relevance_score=95)
                ),
                rule_scores=RuleScoreBreakdown(pipeline_overview=10, overall_score=10),
                llm_scores=LLMScoreBreakdown(pipeline_overview=98, overall_score=98),
                final_scores=FinalScoreBreakdown(pipeline_overview=99, overall_score=99),
                prompt_version="trial_enrichment_v1",
            )
        },
    )

    assert selection.trial_keys[0] == "trial-enriched"
    assert "trial-rule-only" in selection.trial_keys
    assert "trial-low" not in selection.trial_keys


def test_selector_uses_literature_fallback_when_no_enrichment_exists() -> None:
    selector = SectionSelector(research_high_value_limit=1, research_recent_limit=1)
    query = TargetQuery(target="HER2", indication="breast cancer")
    strongest = NormalizedLiteratureRecord(
        literature_key="pmid-strong",
        title="HER2 breast cancer clinical trial review",
        publication_types=["Clinical Trial"],
        keywords=["HER2"],
        mesh_terms=["Breast Neoplasms"],
    )
    weaker = NormalizedLiteratureRecord(
        literature_key="pmid-weak",
        title="General oncology methods",
        publication_types=["Editorial"],
    )

    selection = selector.select_research_update(query, [strongest, weaker])

    assert "pmid-strong" in selection.literature_keys


def test_bundle_builder_can_limit_selector_scope_without_changing_global_stats() -> None:
    builder = AnalysisBundleBuilder(selector=SectionSelector(pipeline_trial_limit=5))
    query = TargetQuery(target="HER2", indication="breast cancer")
    excluded_strong_trial = NormalizedTrialRecord(
        trial_key="trial-excluded",
        brief_title="HER2 phase 3 breast cancer trial",
        conditions=["Breast Cancer"],
        phase="PHASE3",
        overall_status="RECRUITING",
    )
    scoped_trial = NormalizedTrialRecord(
        trial_key="trial-scoped",
        brief_title="Background registry",
        conditions=["Healthy Volunteers"],
        phase="EARLY_PHASE1",
        overall_status="COMPLETED",
    )

    bundle = builder.build(
        query=query,
        trials=[excluded_strong_trial, scoped_trial],
        literature=[],
        selector_trials=[scoped_trial],
        selector_literature=[],
    )

    assert bundle.global_stats.total_trial_count == 2
    assert bundle.coverage.has_trial_evidence is True
    assert bundle.section_inputs.pipeline_overview.trial_keys == ["trial-scoped"]
    assert "trial-excluded" not in bundle.section_inputs.pipeline_overview.trial_keys
