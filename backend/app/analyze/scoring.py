from __future__ import annotations

from datetime import date

from app.domain import NormalizedLiteratureRecord, NormalizedTrialRecord, TargetQuery

ACTIVE_TRIAL_STATUSES = {
    "NOT_YET_RECRUITING",
    "RECRUITING",
    "ENROLLING_BY_INVITATION",
    "ACTIVE_NOT_RECRUITING",
}
LATE_STAGE_PHASES = {"PHASE3", "PHASE4"}
REVIEW_PUBLICATION_TYPES = {"review", "systematic review", "meta-analysis"}
CLINICAL_PUBLICATION_TYPES = {
    "clinical trial",
    "randomized controlled trial",
    "multicenter study",
}


def build_target_terms(query: TargetQuery) -> list[str]:
    return list(dict.fromkeys(term.strip() for term in [query.target, *query.aliases] if term.strip()))


def score_trial_for_pipeline(query: TargetQuery, trial: NormalizedTrialRecord) -> float:
    return (
        score_trial_relevance(query, trial)
        + _phase_weight(trial.phase)
        + _status_weight(trial.overall_status)
        + (5.0 if trial.has_results else 0.0)
    )


def score_trial_for_competition(query: TargetQuery, trial: NormalizedTrialRecord) -> float:
    score = score_trial_for_pipeline(query, trial)
    if trial.lead_sponsor:
        score += 8.0
    if trial.phase in LATE_STAGE_PHASES:
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
        score += _match_score([query.indication], [literature.title, *abstract_texts, *literature.mesh_terms]) * 3.0
    return score


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
