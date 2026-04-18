from __future__ import annotations

from datetime import date

from app.domain import (
    AnalysisDimensionName,
    FinalScoreBreakdown,
    LLMScoreBreakdown,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    RuleScoreBreakdown,
    ScoreBreakdown,
    TargetQuery,
)

ACTIVE_TRIAL_STATUSES = {
    "NOT_YET_RECRUITING",
    "RECRUITING",
    "ENROLLING_BY_INVITATION",
    "ACTIVE_NOT_RECRUITING",
}
REVIEW_PUBLICATION_TYPES = {"review", "systematic review", "meta-analysis"}
CLINICAL_PUBLICATION_TYPES = {
    "clinical trial",
    "randomized controlled trial",
    "multicenter study",
}
TRIAL_OVERALL_WEIGHTS = {
    AnalysisDimensionName.TARGET_OVERVIEW: 0.15,
    AnalysisDimensionName.PIPELINE_OVERVIEW: 0.35,
    AnalysisDimensionName.RESEARCH_UPDATE: 0.10,
    AnalysisDimensionName.COMPETITION_ASSESSMENT: 0.40,
}
LITERATURE_OVERALL_WEIGHTS = {
    AnalysisDimensionName.TARGET_OVERVIEW: 0.30,
    AnalysisDimensionName.PIPELINE_OVERVIEW: 0.10,
    AnalysisDimensionName.RESEARCH_UPDATE: 0.40,
    AnalysisDimensionName.COMPETITION_ASSESSMENT: 0.20,
}


def build_target_terms(query: TargetQuery) -> list[str]:
    return list(
        dict.fromkeys(term.strip() for term in [query.target, *query.aliases] if term.strip())
    )


def build_trial_rule_scores(
    query: TargetQuery,
    trial: NormalizedTrialRecord,
) -> RuleScoreBreakdown:
    target = _normalize_score(score_trial_for_target_overview(query, trial), maximum=30.0)
    pipeline = _normalize_score(score_trial_for_pipeline(query, trial), maximum=60.0)
    research = _normalize_score(score_trial_for_research_update(query, trial), maximum=45.0)
    competition = _normalize_score(score_trial_for_competition(query, trial), maximum=80.0)
    return RuleScoreBreakdown(
        target_overview=target,
        pipeline_overview=pipeline,
        research_update=research,
        competition_assessment=competition,
        overall_score=_weighted_overall(
            {
                AnalysisDimensionName.TARGET_OVERVIEW: target,
                AnalysisDimensionName.PIPELINE_OVERVIEW: pipeline,
                AnalysisDimensionName.RESEARCH_UPDATE: research,
                AnalysisDimensionName.COMPETITION_ASSESSMENT: competition,
            },
            TRIAL_OVERALL_WEIGHTS,
        ),
    )


def build_literature_rule_scores(
    query: TargetQuery,
    literature: NormalizedLiteratureRecord,
) -> RuleScoreBreakdown:
    target = _normalize_score(
        score_literature_for_target_overview(query, literature),
        maximum=50.0,
    )
    pipeline = _normalize_score(
        score_literature_for_pipeline(query, literature),
        maximum=45.0,
    )
    research = _normalize_score(
        score_literature_for_research_update(query, literature),
        maximum=60.0,
    )
    competition = _normalize_score(
        score_literature_for_competition(query, literature),
        maximum=75.0,
    )
    return RuleScoreBreakdown(
        target_overview=target,
        pipeline_overview=pipeline,
        research_update=research,
        competition_assessment=competition,
        overall_score=_weighted_overall(
            {
                AnalysisDimensionName.TARGET_OVERVIEW: target,
                AnalysisDimensionName.PIPELINE_OVERVIEW: pipeline,
                AnalysisDimensionName.RESEARCH_UPDATE: research,
                AnalysisDimensionName.COMPETITION_ASSESSMENT: competition,
            },
            LITERATURE_OVERALL_WEIGHTS,
        ),
    )


def blend_trial_scores(
    rule_scores: RuleScoreBreakdown,
    llm_scores: LLMScoreBreakdown,
) -> FinalScoreBreakdown:
    return _blend_scores(rule_scores, llm_scores, TRIAL_OVERALL_WEIGHTS)


def blend_literature_scores(
    rule_scores: RuleScoreBreakdown,
    llm_scores: LLMScoreBreakdown,
) -> FinalScoreBreakdown:
    return _blend_scores(rule_scores, llm_scores, LITERATURE_OVERALL_WEIGHTS)


def get_dimension_score(
    scores: ScoreBreakdown,
    dimension: AnalysisDimensionName,
) -> float:
    return float(getattr(scores, dimension.value))


def score_trial_for_target_overview(
    query: TargetQuery,
    trial: NormalizedTrialRecord,
) -> float:
    return score_trial_relevance(query, trial)


def score_trial_for_pipeline(query: TargetQuery, trial: NormalizedTrialRecord) -> float:
    return (
        score_trial_relevance(query, trial)
        + _phase_weight(trial.phase)
        + _status_weight(trial.overall_status)
        + (5.0 if trial.has_results else 0.0)
    )


def score_trial_for_research_update(query: TargetQuery, trial: NormalizedTrialRecord) -> float:
    update_date = None
    if trial.last_update_post_date and trial.last_update_post_date.value is not None:
        update_date = trial.last_update_post_date.value
    elif trial.study_first_post_date and trial.study_first_post_date.value is not None:
        update_date = trial.study_first_post_date.value
    score = score_trial_relevance(query, trial)
    score += _recency_score(update_date)
    if trial.has_results:
        score += 8.0
    if trial.primary_outcomes or trial.secondary_outcomes:
        score += 4.0
    return score


def score_trial_for_competition(query: TargetQuery, trial: NormalizedTrialRecord) -> float:
    score = score_trial_for_pipeline(query, trial)
    if trial.lead_sponsor:
        score += 8.0
    if trial.phase and ("PHASE3" in trial.phase or "PHASE4" in trial.phase):
        score += 10.0
    return score


def score_trial_relevance(query: TargetQuery, trial: NormalizedTrialRecord) -> float:
    terms = build_target_terms(query)
    score = 0.0
    score += _match_score(terms, [trial.brief_title, trial.official_title]) * 4.0
    score += _match_score(terms, [trial.summary]) * 2.0
    score += _match_score(terms, trial.conditions) * 3.0
    score += _match_score(
        terms,
        [intervention.name for intervention in trial.interventions],
    ) * 1.5

    if query.indication:
        score += _match_score([query.indication], [trial.summary, *trial.conditions]) * 3.0
    return score


def score_literature_for_target_overview(
    query: TargetQuery,
    literature: NormalizedLiteratureRecord,
) -> float:
    score = score_literature_relevance(query, literature)
    if _publication_type_matches(literature, REVIEW_PUBLICATION_TYPES):
        score += 18.0
    return score


def score_literature_for_pipeline(
    query: TargetQuery,
    literature: NormalizedLiteratureRecord,
) -> float:
    score = score_literature_relevance(query, literature)
    if _publication_type_matches(literature, CLINICAL_PUBLICATION_TYPES):
        score += 12.0
    if literature.linked_nct_ids:
        score += 8.0
    return score


def score_literature_for_research_update(
    query: TargetQuery,
    literature: NormalizedLiteratureRecord,
) -> float:
    score = score_literature_relevance(query, literature)
    score += _recency_score(literature.publication_date.value if literature.publication_date else None)
    if _publication_type_matches(literature, CLINICAL_PUBLICATION_TYPES):
        score += 12.0
    if literature.linked_nct_ids:
        score += 6.0
    return score


def score_literature_for_competition(
    query: TargetQuery,
    literature: NormalizedLiteratureRecord,
) -> float:
    score = score_literature_for_research_update(query, literature)
    if literature.linked_nct_ids:
        score += 10.0
    return score


def score_literature_relevance(query: TargetQuery, literature: NormalizedLiteratureRecord) -> float:
    terms = build_target_terms(query)
    abstract_texts = [section.text for section in literature.abstract_sections]
    score = 0.0
    score += _match_score(terms, [literature.title]) * 5.0
    score += _match_score(terms, abstract_texts) * 2.5
    score += _match_score(terms, literature.mesh_terms) * 2.0
    score += _match_score(terms, literature.keywords) * 2.0
    if query.indication:
        score += _match_score(
            [query.indication],
            [literature.title, *abstract_texts, *literature.mesh_terms],
        ) * 3.0
    return score


def _blend_scores(
    rule_scores: RuleScoreBreakdown,
    llm_scores: LLMScoreBreakdown,
    weights: dict[AnalysisDimensionName, float],
) -> FinalScoreBreakdown:
    target = _blend_dimension_score(rule_scores.target_overview, llm_scores.target_overview)
    pipeline = _blend_dimension_score(
        rule_scores.pipeline_overview,
        llm_scores.pipeline_overview,
    )
    research = _blend_dimension_score(
        rule_scores.research_update,
        llm_scores.research_update,
    )
    competition = _blend_dimension_score(
        rule_scores.competition_assessment,
        llm_scores.competition_assessment,
    )
    return FinalScoreBreakdown(
        target_overview=target,
        pipeline_overview=pipeline,
        research_update=research,
        competition_assessment=competition,
        overall_score=_weighted_overall(
            {
                AnalysisDimensionName.TARGET_OVERVIEW: target,
                AnalysisDimensionName.PIPELINE_OVERVIEW: pipeline,
                AnalysisDimensionName.RESEARCH_UPDATE: research,
                AnalysisDimensionName.COMPETITION_ASSESSMENT: competition,
            },
            weights,
        ),
    )


def _blend_dimension_score(rule_score: float, llm_score: float) -> float:
    return round((0.65 * rule_score) + (0.35 * llm_score), 2)


def _weighted_overall(
    scores: dict[AnalysisDimensionName, float],
    weights: dict[AnalysisDimensionName, float],
) -> float:
    total = sum(scores[dimension] * weights[dimension] for dimension in weights)
    return round(total, 2)


def _normalize_score(raw_score: float, *, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return round(min(max(raw_score, 0.0), maximum) / maximum * 100.0, 2)


def _match_score(terms: list[str], texts: list[str | None]) -> float:
    normalized_text = " ".join(text.casefold() for text in texts if text)
    score = 0.0
    for term in terms:
        if term.casefold() in normalized_text:
            score += 1.0
    return score


def _phase_weight(phase: str | None) -> float:
    if phase is None:
        return 0.0
    if "PHASE4" in phase:
        return 16.0
    if "PHASE3" in phase:
        return 14.0
    if "PHASE2" in phase:
        return 10.0
    if "PHASE1" in phase:
        return 6.0
    return 2.0


def _status_weight(status: str | None) -> float:
    if status is None:
        return 0.0
    if status in ACTIVE_TRIAL_STATUSES:
        return 12.0
    return 2.0


def _recency_score(publication_date: date | None) -> float:
    if publication_date is None:
        return 0.0
    years_old = max(date.today().year - publication_date.year, 0)
    if years_old <= 1:
        return 12.0
    if years_old <= 3:
        return 8.0
    if years_old <= 5:
        return 4.0
    return 0.0


def _publication_type_matches(
    literature: NormalizedLiteratureRecord,
    candidates: set[str],
) -> bool:
    normalized_types = {item.casefold() for item in literature.publication_types}
    return bool(normalized_types & candidates)
