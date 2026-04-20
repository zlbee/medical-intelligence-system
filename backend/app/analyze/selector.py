from __future__ import annotations

from dataclasses import dataclass, field

from app.analyze.scoring import (
    build_literature_rule_scores,
    build_trial_rule_scores,
    get_dimension_score,
)
from app.domain import (
    AnalysisDimensionName,
    LiteratureLLMEnrichment,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    TargetQuery,
    TrialLLMEnrichment,
)
from app.normalize.common import unique_strings


@dataclass(slots=True)
class SectionSelection:
    trial_keys: list[str] = field(default_factory=list)
    literature_keys: list[str] = field(default_factory=list)
    selection_notes: list[str] = field(default_factory=list)
    truncation_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResearchSelection(SectionSelection):
    recent_paper_keys: list[str] = field(default_factory=list)
    high_value_paper_keys: list[str] = field(default_factory=list)


class SectionSelector:
    def __init__(
        self,
        *,
        target_overview_literature_limit: int = 12,
        target_overview_trial_limit: int = 5,
        pipeline_trial_limit: int = 20,
        research_recent_limit: int = 10,
        research_high_value_limit: int = 10,
        competition_trial_limit: int = 10,
        competition_literature_limit: int = 8,
    ) -> None:
        self.target_overview_literature_limit = target_overview_literature_limit
        self.target_overview_trial_limit = target_overview_trial_limit
        self.pipeline_trial_limit = pipeline_trial_limit
        self.research_recent_limit = research_recent_limit
        self.research_high_value_limit = research_high_value_limit
        self.competition_trial_limit = competition_trial_limit
        self.competition_literature_limit = competition_literature_limit

    def select_target_overview(
        self,
        query: TargetQuery,
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
        *,
        trial_enrichments_by_key: dict[str, TrialLLMEnrichment] | None = None,
        literature_enrichments_by_key: dict[str, LiteratureLLMEnrichment] | None = None,
    ) -> SectionSelection:
        ranked_literature = sorted(
            literature,
            key=lambda item: (
                self._literature_dimension_score(
                    query,
                    item,
                    AnalysisDimensionName.TARGET_OVERVIEW,
                    literature_enrichments_by_key,
                ),
                self._publication_ordinal(item),
            ),
            reverse=True,
        )
        ranked_trials = sorted(
            trials,
            key=lambda item: self._trial_dimension_score(
                query,
                item,
                AnalysisDimensionName.TARGET_OVERVIEW,
                trial_enrichments_by_key,
            ),
            reverse=True,
        )
        selected_literature = ranked_literature[: self.target_overview_literature_limit]
        selected_trials = ranked_trials[: self.target_overview_trial_limit]
        selection = SectionSelection(
            trial_keys=[trial.trial_key for trial in selected_trials],
            literature_keys=[paper.literature_key for paper in selected_literature],
            selection_notes=[
                "Prefer literature with strong target-overview fusion scores for mechanism and context.",
                "Keep a small number of trial references to anchor disease and intervention context.",
            ],
        )
        if len(ranked_literature) > len(selected_literature):
            selection.truncation_notes.append(
                f"Selected top {len(selected_literature)} of {len(ranked_literature)} literature records for target overview."
            )
        if len(ranked_trials) > len(selected_trials):
            selection.truncation_notes.append(
                f"Selected top {len(selected_trials)} of {len(ranked_trials)} trial records for target context."
            )
        return selection

    def select_pipeline_overview(
        self,
        query: TargetQuery,
        trials: list[NormalizedTrialRecord],
        *,
        trial_enrichments_by_key: dict[str, TrialLLMEnrichment] | None = None,
    ) -> SectionSelection:
        ranked_trials = sorted(
            trials,
            key=lambda item: self._trial_dimension_score(
                query,
                item,
                AnalysisDimensionName.PIPELINE_OVERVIEW,
                trial_enrichments_by_key,
            ),
            reverse=True,
        )
        selected_trials = ranked_trials[: self.pipeline_trial_limit]
        selection = SectionSelection(
            trial_keys=[trial.trial_key for trial in selected_trials],
            selection_notes=[
                "Rank trials by pipeline fusion score with rule-score fallback when LLM enrichment is unavailable.",
            ],
        )
        if len(ranked_trials) > len(selected_trials):
            selection.truncation_notes.append(
                f"Selected top {len(selected_trials)} of {len(ranked_trials)} trial records for pipeline overview."
            )
        return selection

    def select_research_update(
        self,
        query: TargetQuery,
        literature: list[NormalizedLiteratureRecord],
        *,
        literature_enrichments_by_key: dict[str, LiteratureLLMEnrichment] | None = None,
    ) -> ResearchSelection:
        recent_ranked = sorted(
            literature,
            key=lambda item: (
                self._publication_ordinal(item),
                self._literature_dimension_score(
                    query,
                    item,
                    AnalysisDimensionName.RESEARCH_UPDATE,
                    literature_enrichments_by_key,
                ),
            ),
            reverse=True,
        )
        high_value_ranked = sorted(
            literature,
            key=lambda item: self._literature_dimension_score(
                query,
                item,
                AnalysisDimensionName.RESEARCH_UPDATE,
                literature_enrichments_by_key,
            ),
            reverse=True,
        )
        recent_papers = recent_ranked[: self.research_recent_limit]
        high_value_papers = high_value_ranked[: self.research_high_value_limit]
        literature_keys = unique_strings(
            [paper.literature_key for paper in [*recent_papers, *high_value_papers]]
        )
        selection = ResearchSelection(
            literature_keys=literature_keys,
            recent_paper_keys=[paper.literature_key for paper in recent_papers],
            high_value_paper_keys=[paper.literature_key for paper in high_value_papers],
            selection_notes=[
                "Keep both the newest papers and the highest-value papers so recency does not hide stronger evidence.",
            ],
        )
        if len(recent_ranked) > len(recent_papers):
            selection.truncation_notes.append(
                f"Selected most recent {len(recent_papers)} of {len(recent_ranked)} literature records."
            )
        if len(high_value_ranked) > len(high_value_papers):
            selection.truncation_notes.append(
                f"Selected highest-value {len(high_value_papers)} of {len(high_value_ranked)} literature records."
            )
        return selection

    def select_competition_assessment(
        self,
        query: TargetQuery,
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
        *,
        trial_enrichments_by_key: dict[str, TrialLLMEnrichment] | None = None,
        literature_enrichments_by_key: dict[str, LiteratureLLMEnrichment] | None = None,
    ) -> SectionSelection:
        ranked_trials = sorted(
            trials,
            key=lambda item: self._trial_dimension_score(
                query,
                item,
                AnalysisDimensionName.COMPETITION_ASSESSMENT,
                trial_enrichments_by_key,
            ),
            reverse=True,
        )
        ranked_literature = sorted(
            literature,
            key=lambda item: self._literature_dimension_score(
                query,
                item,
                AnalysisDimensionName.COMPETITION_ASSESSMENT,
                literature_enrichments_by_key,
            ),
            reverse=True,
        )
        selected_trials = ranked_trials[: self.competition_trial_limit]
        selected_literature = ranked_literature[: self.competition_literature_limit]
        selection = SectionSelection(
            trial_keys=[trial.trial_key for trial in selected_trials],
            literature_keys=[paper.literature_key for paper in selected_literature],
            selection_notes=[
                "Prefer trials with strong competition fusion scores and sponsor-identifiable late-stage activity.",
                "Keep literature with strong competition relevance or explicit NCT mentions as supporting evidence.",
            ],
        )
        if len(ranked_trials) > len(selected_trials):
            selection.truncation_notes.append(
                f"Selected top {len(selected_trials)} of {len(ranked_trials)} trial records for competition assessment."
            )
        if len(ranked_literature) > len(selected_literature):
            selection.truncation_notes.append(
                f"Selected top {len(selected_literature)} of {len(ranked_literature)} literature records for competition assessment."
            )
        return selection

    def _trial_dimension_score(
        self,
        query: TargetQuery,
        trial: NormalizedTrialRecord,
        dimension: AnalysisDimensionName,
        enrichments_by_key: dict[str, TrialLLMEnrichment] | None,
    ) -> float:
        if enrichments_by_key and trial.trial_key in enrichments_by_key:
            return get_dimension_score(enrichments_by_key[trial.trial_key].final_scores, dimension)
        return get_dimension_score(build_trial_rule_scores(query, trial), dimension)

    def _literature_dimension_score(
        self,
        query: TargetQuery,
        literature: NormalizedLiteratureRecord,
        dimension: AnalysisDimensionName,
        enrichments_by_key: dict[str, LiteratureLLMEnrichment] | None,
    ) -> float:
        if enrichments_by_key and literature.literature_key in enrichments_by_key:
            return get_dimension_score(
                enrichments_by_key[literature.literature_key].final_scores,
                dimension,
            )
        return get_dimension_score(build_literature_rule_scores(query, literature), dimension)

    def _publication_ordinal(self, literature: NormalizedLiteratureRecord) -> int:
        if literature.publication_date and literature.publication_date.value:
            return literature.publication_date.value.toordinal()
        return 0
