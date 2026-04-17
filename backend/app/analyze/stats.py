from __future__ import annotations

from collections import Counter, defaultdict

from app.domain import (
    CompetitionAssessmentFacts,
    GlobalAnalysisStats,
    NamedCount,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    PipelineOverviewFacts,
    ResearchUpdateFacts,
    SponsorPhaseRow,
    TargetOverviewFacts,
    TargetQuery,
)
from app.normalize.common import unique_strings


def build_global_analysis_stats(
    trials: list[NormalizedTrialRecord],
    literature: list[NormalizedLiteratureRecord],
) -> GlobalAnalysisStats:
    return GlobalAnalysisStats(
        total_trial_count=len(trials),
        total_literature_count=len(literature),
        trial_phase_distribution=_counter_dict(trial.phase for trial in trials if trial.phase),
        trial_status_distribution=_counter_dict(
            trial.overall_status for trial in trials if trial.overall_status
        ),
        top_sponsors=_top_named_counts(
            [trial.lead_sponsor for trial in trials if trial.lead_sponsor]
        ),
        top_interventions=_top_named_counts(
            intervention.name
            for trial in trials
            for intervention in trial.interventions
        ),
        top_conditions=_top_named_counts(
            condition
            for trial in trials
            for condition in trial.conditions
        ),
        top_countries=_top_named_counts(
            country
            for trial in trials
            for country in trial.countries
        ),
        publication_count_by_year=_counter_int_dict(
            literature_item.publication_date.value.year
            for literature_item in literature
            if literature_item.publication_date and literature_item.publication_date.value
        ),
        publication_type_distribution=_counter_dict(
            publication_type
            for literature_item in literature
            for publication_type in literature_item.publication_types
        ),
        top_journals=_top_named_counts(
            literature_item.journal
            for literature_item in literature
            if literature_item.journal
        ),
        top_mesh_terms=_top_named_counts(
            mesh_term
            for literature_item in literature
            for mesh_term in literature_item.mesh_terms
        ),
        top_keywords=_top_named_counts(
            keyword
            for literature_item in literature
            for keyword in literature_item.keywords
        ),
        literature_with_nct_mentions_count=sum(
            1 for literature_item in literature if literature_item.linked_nct_ids
        ),
    )


def build_target_overview_facts(
    query: TargetQuery,
    trials: list[NormalizedTrialRecord],
    literature: list[NormalizedLiteratureRecord],
    *,
    representative_paper_keys: list[str],
) -> TargetOverviewFacts:
    flattened_disease_contexts = [
        condition
        for trial in trials
        for condition in trial.conditions[:2]
    ]
    if query.indication:
        flattened_disease_contexts.append(query.indication)

    return TargetOverviewFacts(
        alias_terms=unique_strings([query.target, *query.aliases]),
        disease_contexts=unique_strings(flattened_disease_contexts),
        top_mesh_terms=_top_named_counts(
            mesh_term
            for literature_item in literature
            for mesh_term in literature_item.mesh_terms
        ),
        top_keywords=_top_named_counts(
            keyword
            for literature_item in literature
            for keyword in literature_item.keywords
        ),
        publication_type_distribution=_counter_dict(
            publication_type
            for literature_item in literature
            for publication_type in literature_item.publication_types
        ),
        representative_paper_keys=representative_paper_keys,
    )


def build_pipeline_overview_facts(
    trials: list[NormalizedTrialRecord],
) -> PipelineOverviewFacts:
    active_statuses = {
        "NOT_YET_RECRUITING",
        "RECRUITING",
        "ENROLLING_BY_INVITATION",
        "ACTIVE_NOT_RECRUITING",
    }
    return PipelineOverviewFacts(
        phase_distribution=_counter_dict(trial.phase for trial in trials if trial.phase),
        status_distribution=_counter_dict(
            trial.overall_status for trial in trials if trial.overall_status
        ),
        top_sponsors=_top_named_counts(
            trial.lead_sponsor
            for trial in trials
            if trial.lead_sponsor
        ),
        top_interventions=_top_named_counts(
            intervention.name
            for trial in trials
            for intervention in trial.interventions
        ),
        top_conditions=_top_named_counts(
            condition
            for trial in trials
            for condition in trial.conditions
        ),
        country_distribution=_top_named_counts(
            country
            for trial in trials
            for country in trial.countries
        ),
        active_trial_count=sum(
            1 for trial in trials if trial.overall_status in active_statuses
        ),
        results_posted_count=sum(1 for trial in trials if trial.has_results),
    )


def build_research_update_facts(
    literature: list[NormalizedLiteratureRecord],
    *,
    recent_paper_keys: list[str],
    high_value_paper_keys: list[str],
) -> ResearchUpdateFacts:
    return ResearchUpdateFacts(
        publication_count_by_year=_counter_int_dict(
            literature_item.publication_date.value.year
            for literature_item in literature
            if literature_item.publication_date and literature_item.publication_date.value
        ),
        publication_type_distribution=_counter_dict(
            publication_type
            for literature_item in literature
            for publication_type in literature_item.publication_types
        ),
        top_journals=_top_named_counts(
            literature_item.journal
            for literature_item in literature
            if literature_item.journal
        ),
        top_mesh_terms=_top_named_counts(
            mesh_term
            for literature_item in literature
            for mesh_term in literature_item.mesh_terms
        ),
        top_keywords=_top_named_counts(
            keyword
            for literature_item in literature
            for keyword in literature_item.keywords
        ),
        recent_paper_keys=recent_paper_keys,
        high_value_paper_keys=high_value_paper_keys,
    )


def build_competition_assessment_facts(
    trials: list[NormalizedTrialRecord],
    literature: list[NormalizedLiteratureRecord],
) -> CompetitionAssessmentFacts:
    sponsor_phase_map: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for trial in trials:
        sponsor = trial.lead_sponsor
        phase = trial.phase or "UNKNOWN"
        if sponsor is None:
            continue
        sponsor_phase_map[sponsor][phase] += 1

    sponsor_rows = [
        SponsorPhaseRow(
            sponsor=sponsor,
            phase_counts=dict(sorted(phase_counts.items())),
            total_trials=sum(phase_counts.values()),
        )
        for sponsor, phase_counts in sponsor_phase_map.items()
    ]
    sponsor_rows.sort(key=lambda item: (-item.total_trials, item.sponsor.casefold()))

    late_stage_trial_count = sum(
        1 for trial in trials if trial.phase and ("PHASE3" in trial.phase or "PHASE4" in trial.phase)
    )
    recruiting_trial_count = sum(
        1 for trial in trials if trial.overall_status == "RECRUITING"
    )

    return CompetitionAssessmentFacts(
        sponsor_phase_matrix=sponsor_rows[:10],
        active_sponsor_count=len({trial.lead_sponsor for trial in trials if trial.lead_sponsor}),
        late_stage_trial_count=late_stage_trial_count,
        recruiting_trial_count=recruiting_trial_count,
        results_posted_count=sum(1 for trial in trials if trial.has_results),
        literature_with_nct_mentions_count=sum(
            1 for literature_item in literature if literature_item.linked_nct_ids
        ),
        sponsor_concentration=_top_named_counts(
            trial.lead_sponsor
            for trial in trials
            if trial.lead_sponsor
        ),
    )


def _top_named_counts(values, *, limit: int = 10) -> list[NamedCount]:
    counter = Counter(value for value in values if value)
    return [
        NamedCount(name=name, count=count)
        for name, count in counter.most_common(limit)
    ]


def _counter_dict(values) -> dict[str, int]:
    counter = Counter(value for value in values if value)
    return dict(counter)


def _counter_int_dict(values) -> dict[int, int]:
    counter = Counter(value for value in values if value is not None)
    return dict(sorted(counter.items()))
