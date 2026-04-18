from __future__ import annotations

from app.analyze.scoring import (
    blend_literature_scores,
    blend_trial_scores,
    build_literature_rule_scores,
    build_trial_rule_scores,
)
from app.domain import (
    AbstractSection,
    LLMScoreBreakdown,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    TargetQuery,
)


def test_blended_trial_scores_follow_fixed_formula_and_weights() -> None:
    rule_scores = build_trial_rule_scores(
        TargetQuery(target="HER2", indication="breast cancer"),
        NormalizedTrialRecord(
            trial_key="NCT00000001",
            brief_title="HER2 trial",
            summary="Breast cancer study",
            conditions=["Breast Cancer"],
            phase="PHASE2",
            overall_status="RECRUITING",
            has_results=True,
        ),
    )
    llm_scores = LLMScoreBreakdown(
        target_overview=50,
        pipeline_overview=60,
        research_update=70,
        competition_assessment=80,
        overall_score=65,
    )

    final_scores = blend_trial_scores(rule_scores, llm_scores)

    assert final_scores.target_overview == round(
        (0.65 * rule_scores.target_overview) + (0.35 * 50),
        2,
    )
    assert final_scores.pipeline_overview == round(
        (0.65 * rule_scores.pipeline_overview) + (0.35 * 60),
        2,
    )
    assert final_scores.overall_score == round(
        final_scores.target_overview * 0.15
        + final_scores.pipeline_overview * 0.35
        + final_scores.research_update * 0.10
        + final_scores.competition_assessment * 0.40,
        2,
    )


def test_literature_rule_scores_are_normalized_to_percentage_range() -> None:
    scores = build_literature_rule_scores(
        TargetQuery(target="HER2", indication="breast cancer"),
        NormalizedLiteratureRecord(
            literature_key="12345678",
            title="HER2 review in breast cancer",
            publication_types=["Review", "Clinical Trial"],
            abstract_sections=[AbstractSection(text="HER2 breast cancer update.")],
            mesh_terms=["Breast Neoplasms"],
            keywords=["HER2"],
            linked_nct_ids=["NCT03188393"],
        ),
    )
    final_scores = blend_literature_scores(
        scores,
        LLMScoreBreakdown(
            target_overview=70,
            pipeline_overview=40,
            research_update=80,
            competition_assessment=50,
            overall_score=60,
        ),
    )

    for value in (
        scores.target_overview,
        scores.pipeline_overview,
        scores.research_update,
        scores.competition_assessment,
        scores.overall_score,
        final_scores.overall_score,
    ):
        assert 0 <= value <= 100
