from __future__ import annotations

from app.analyze.selector import ResearchSelection, SectionSelection, SectionSelector
from app.analyze.stats import (
    build_competition_assessment_facts,
    build_global_analysis_stats,
    build_pipeline_overview_facts,
    build_research_update_facts,
    build_target_overview_facts,
)
from app.domain import (
    AnalysisReadyBundle,
    CompetitionAssessmentSectionInput,
    CoverageSnapshot,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    PipelineOverviewSectionInput,
    ResearchUpdateSectionInput,
    SectionInputBundle,
    TargetOverviewSectionInput,
    TargetQuery,
    WarningItem,
    WarningLevel,
    WarningScope,
)


class AnalysisBundleBuilder:
    def __init__(self, *, selector: SectionSelector | None = None) -> None:
        self.selector = selector or SectionSelector()

    def build(
        self,
        *,
        query: TargetQuery,
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
    ) -> AnalysisReadyBundle:
        global_stats = build_global_analysis_stats(trials, literature)

        target_selection = self.selector.select_target_overview(query, trials, literature)
        pipeline_selection = self.selector.select_pipeline_overview(query, trials)
        research_selection = self.selector.select_research_update(query, literature)
        competition_selection = self.selector.select_competition_assessment(
            query,
            trials,
            literature,
        )

        section_inputs = SectionInputBundle(
            target_overview=self._build_target_overview_section(
                query,
                trials,
                literature,
                target_selection,
            ),
            pipeline_overview=self._build_pipeline_overview_section(trials, pipeline_selection),
            research_update=self._build_research_update_section(literature, research_selection),
            competition_assessment=self._build_competition_section(
                trials,
                literature,
                competition_selection,
            ),
        )
        coverage = self._build_coverage(section_inputs, trials, literature)
        warnings = self._build_warnings(section_inputs, coverage)

        return AnalysisReadyBundle(
            query=query,
            trials=trials,
            literature=literature,
            global_stats=global_stats,
            coverage=coverage,
            section_inputs=section_inputs,
            warnings=warnings,
        )

    def _build_target_overview_section(
        self,
        query: TargetQuery,
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
        selection: SectionSelection,
    ) -> TargetOverviewSectionInput:
        warnings = []
        if not selection.literature_keys:
            warnings.append("No literature evidence selected for target overview.")
        return TargetOverviewSectionInput(
            trial_keys=selection.trial_keys,
            literature_keys=selection.literature_keys,
            selection_notes=selection.selection_notes,
            truncation_notes=selection.truncation_notes,
            warnings=warnings,
            facts=build_target_overview_facts(
                query,
                trials,
                literature,
                representative_paper_keys=selection.literature_keys,
            ),
        )

    def _build_pipeline_overview_section(
        self,
        trials: list[NormalizedTrialRecord],
        selection: SectionSelection,
    ) -> PipelineOverviewSectionInput:
        warnings = []
        if not selection.trial_keys:
            warnings.append("No trial evidence selected for pipeline overview.")
        return PipelineOverviewSectionInput(
            trial_keys=selection.trial_keys,
            literature_keys=selection.literature_keys,
            selection_notes=selection.selection_notes,
            truncation_notes=selection.truncation_notes,
            warnings=warnings,
            facts=build_pipeline_overview_facts(trials),
        )

    def _build_research_update_section(
        self,
        literature: list[NormalizedLiteratureRecord],
        selection: ResearchSelection,
    ) -> ResearchUpdateSectionInput:
        warnings = []
        if not selection.literature_keys:
            warnings.append("No literature evidence selected for research update.")
        return ResearchUpdateSectionInput(
            trial_keys=selection.trial_keys,
            literature_keys=selection.literature_keys,
            selection_notes=selection.selection_notes,
            truncation_notes=selection.truncation_notes,
            warnings=warnings,
            facts=build_research_update_facts(
                literature,
                recent_paper_keys=selection.recent_paper_keys,
                high_value_paper_keys=selection.high_value_paper_keys,
            ),
        )

    def _build_competition_section(
        self,
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
        selection: SectionSelection,
    ) -> CompetitionAssessmentSectionInput:
        warnings = []
        if not selection.trial_keys:
            warnings.append("No trial evidence selected for competition assessment.")
        return CompetitionAssessmentSectionInput(
            trial_keys=selection.trial_keys,
            literature_keys=selection.literature_keys,
            selection_notes=selection.selection_notes,
            truncation_notes=selection.truncation_notes,
            warnings=warnings,
            facts=build_competition_assessment_facts(trials, literature),
        )

    def _build_coverage(
        self,
        section_inputs: SectionInputBundle,
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
    ) -> CoverageSnapshot:
        missing_dimensions: list[str] = []
        notes: list[str] = []

        target_has_evidence = bool(section_inputs.target_overview.literature_keys)
        pipeline_has_evidence = bool(section_inputs.pipeline_overview.trial_keys)
        research_has_evidence = bool(section_inputs.research_update.literature_keys)
        competition_has_evidence = bool(
            section_inputs.competition_assessment.trial_keys
            or section_inputs.competition_assessment.literature_keys
        )

        for name, enabled in (
            ("target_overview", target_has_evidence),
            ("pipeline_overview", pipeline_has_evidence),
            ("research_update", research_has_evidence),
            ("competition_assessment", competition_has_evidence),
        ):
            if enabled:
                continue
            missing_dimensions.append(name)
            notes.append(f"{name} currently lacks enough selected evidence.")

        return CoverageSnapshot(
            has_trial_evidence=bool(trials),
            has_literature_evidence=bool(literature),
            has_target_overview_evidence=target_has_evidence,
            has_pipeline_overview_evidence=pipeline_has_evidence,
            has_research_update_evidence=research_has_evidence,
            has_competition_assessment_evidence=competition_has_evidence,
            missing_dimensions=missing_dimensions,
            notes=notes,
        )

    def _build_warnings(
        self,
        section_inputs: SectionInputBundle,
        coverage: CoverageSnapshot,
    ) -> list[WarningItem]:
        warnings: list[WarningItem] = []
        for section_name, section in (
            ("target_overview", section_inputs.target_overview),
            ("pipeline_overview", section_inputs.pipeline_overview),
            ("research_update", section_inputs.research_update),
            ("competition_assessment", section_inputs.competition_assessment),
        ):
            for warning in section.warnings:
                warnings.append(
                    WarningItem(
                        code=f"{section_name}_evidence_gap",
                        level=WarningLevel.WARNING,
                        scope=WarningScope.SECTION,
                        message=warning,
                        related_ids=[section_name],
                    )
                )

        if coverage.missing_dimensions:
            warnings.append(
                WarningItem(
                    code="bundle_incomplete_coverage",
                    level=WarningLevel.WARNING,
                    scope=WarningScope.BUNDLE,
                    message="One or more report sections do not yet have enough selected evidence.",
                    related_ids=coverage.missing_dimensions,
                    details={"missing_dimensions": coverage.missing_dimensions},
                )
            )
        return warnings
