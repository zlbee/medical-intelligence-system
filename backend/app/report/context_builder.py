from __future__ import annotations

from pydantic import BaseModel

from app.domain import (
    AnalysisDimensionName,
    AnalysisReadyBundle,
    LiteratureLLMEnrichment,
    ReportSourceType,
    SECTION_TITLES,
    SectionGenerationContext,
    TrialLLMEnrichment,
    WarningItem,
    WarningLevel,
    WarningScope,
)
from app.infra.exceptions import AppException
from app.repository import (
    AnalysisSnapshotRepository,
    LiteratureLLMEnrichmentRepository,
    TrialLLMEnrichmentRepository,
)


class ReportContextBuilder:
    """Builds section-scoped report inputs from persisted stage-2 artifacts only."""

    def __init__(
        self,
        *,
        analysis_snapshot_repository: AnalysisSnapshotRepository,
        trial_llm_enrichment_repository: TrialLLMEnrichmentRepository,
        literature_llm_enrichment_repository: LiteratureLLMEnrichmentRepository,
    ) -> None:
        self.analysis_snapshot_repository = analysis_snapshot_repository
        self.trial_llm_enrichment_repository = trial_llm_enrichment_repository
        self.literature_llm_enrichment_repository = literature_llm_enrichment_repository

    def build(
        self,
        fetch_run_id: str,
    ) -> tuple[AnalysisReadyBundle, dict[AnalysisDimensionName, SectionGenerationContext], list[WarningItem]]:
        bundle = self.analysis_snapshot_repository.get(fetch_run_id)
        if bundle is None:
            raise AppException(
                "Analysis snapshot is required before generating a report.",
                code="analysis_snapshot_required",
                status_code=409,
                details={"fetch_run_id": fetch_run_id},
            )

        trial_enrichments = self.trial_llm_enrichment_repository.list_by_fetch_run(fetch_run_id)
        literature_enrichments = self.literature_llm_enrichment_repository.list_by_fetch_run(
            fetch_run_id
        )
        trial_map = {record.trial_key: record for record in bundle.trials}
        literature_map = {record.literature_key: record for record in bundle.literature}
        trial_enrichment_map = {record.trial_key: record for record in trial_enrichments}
        literature_enrichment_map = {
            record.literature_key: record for record in literature_enrichments
        }

        warnings: list[WarningItem] = []
        contexts = {
            AnalysisDimensionName.TARGET_OVERVIEW: self._build_section_context(
                fetch_run_id=fetch_run_id,
                bundle=bundle,
                section_name=AnalysisDimensionName.TARGET_OVERVIEW,
                section_input=bundle.section_inputs.target_overview,
                trial_map=trial_map,
                literature_map=literature_map,
                trial_enrichment_map=trial_enrichment_map,
                literature_enrichment_map=literature_enrichment_map,
                warnings=warnings,
            ),
            AnalysisDimensionName.PIPELINE_OVERVIEW: self._build_section_context(
                fetch_run_id=fetch_run_id,
                bundle=bundle,
                section_name=AnalysisDimensionName.PIPELINE_OVERVIEW,
                section_input=bundle.section_inputs.pipeline_overview,
                trial_map=trial_map,
                literature_map=literature_map,
                trial_enrichment_map=trial_enrichment_map,
                literature_enrichment_map=literature_enrichment_map,
                warnings=warnings,
            ),
            AnalysisDimensionName.RESEARCH_UPDATE: self._build_section_context(
                fetch_run_id=fetch_run_id,
                bundle=bundle,
                section_name=AnalysisDimensionName.RESEARCH_UPDATE,
                section_input=bundle.section_inputs.research_update,
                trial_map=trial_map,
                literature_map=literature_map,
                trial_enrichment_map=trial_enrichment_map,
                literature_enrichment_map=literature_enrichment_map,
                warnings=warnings,
            ),
            AnalysisDimensionName.COMPETITION_ASSESSMENT: self._build_section_context(
                fetch_run_id=fetch_run_id,
                bundle=bundle,
                section_name=AnalysisDimensionName.COMPETITION_ASSESSMENT,
                section_input=bundle.section_inputs.competition_assessment,
                trial_map=trial_map,
                literature_map=literature_map,
                trial_enrichment_map=trial_enrichment_map,
                literature_enrichment_map=literature_enrichment_map,
                warnings=warnings,
            ),
        }
        return bundle, contexts, warnings

    def _build_section_context(
        self,
        *,
        fetch_run_id: str,
        bundle: AnalysisReadyBundle,
        section_name: AnalysisDimensionName,
        section_input,
        trial_map: dict[str, object],
        literature_map: dict[str, object],
        trial_enrichment_map: dict[str, TrialLLMEnrichment],
        literature_enrichment_map: dict[str, LiteratureLLMEnrichment],
        warnings: list[WarningItem],
    ) -> SectionGenerationContext:
        context_warnings = list(section_input.warnings)
        selected_trials = []
        selected_literature = []
        selected_trial_enrichments = []
        selected_literature_enrichments = []

        for key in section_input.trial_keys:
            trial = trial_map.get(key)
            if trial is None:
                self._append_missing_reference_warning(
                    warnings=warnings,
                    context_warnings=context_warnings,
                    section_name=section_name,
                    source_type=ReportSourceType.TRIAL,
                    record_key=key,
                    message="Selected trial key is missing from the persisted analysis bundle.",
                )
                continue
            selected_trials.append(trial)
            enrichment = trial_enrichment_map.get(key)
            if enrichment is None:
                self._append_missing_reference_warning(
                    warnings=warnings,
                    context_warnings=context_warnings,
                    section_name=section_name,
                    source_type=ReportSourceType.TRIAL,
                    record_key=key,
                    message="Selected trial key has no persisted LLM enrichment; report generation will continue with deterministic fields only.",
                )
                continue
            selected_trial_enrichments.append(enrichment)

        for key in section_input.literature_keys:
            paper = literature_map.get(key)
            if paper is None:
                self._append_missing_reference_warning(
                    warnings=warnings,
                    context_warnings=context_warnings,
                    section_name=section_name,
                    source_type=ReportSourceType.LITERATURE,
                    record_key=key,
                    message="Selected literature key is missing from the persisted analysis bundle.",
                )
                continue
            selected_literature.append(paper)
            enrichment = literature_enrichment_map.get(key)
            if enrichment is None:
                self._append_missing_reference_warning(
                    warnings=warnings,
                    context_warnings=context_warnings,
                    section_name=section_name,
                    source_type=ReportSourceType.LITERATURE,
                    record_key=key,
                    message="Selected literature key has no persisted LLM enrichment; report generation will continue with deterministic fields only.",
                )
                continue
            selected_literature_enrichments.append(enrichment)

        coverage_notes = []
        if section_name.value in bundle.coverage.missing_dimensions:
            coverage_notes.extend(bundle.coverage.notes)

        return SectionGenerationContext(
            fetch_run_id=fetch_run_id,
            analysis_bundle_id=bundle.bundle_id,
            section_name=section_name,
            title=SECTION_TITLES[section_name],
            query=bundle.query,
            facts=section_input.facts.model_dump(mode="json"),
            global_stats=self._build_relevant_global_stats(bundle, section_name),
            selection_notes=section_input.selection_notes,
            truncation_notes=section_input.truncation_notes,
            warnings=context_warnings,
            coverage_notes=coverage_notes,
            trials=selected_trials,
            literature=selected_literature,
            trial_enrichments=selected_trial_enrichments,
            literature_enrichments=selected_literature_enrichments,
        )

    def _build_relevant_global_stats(
        self,
        bundle: AnalysisReadyBundle,
        section_name: AnalysisDimensionName,
    ) -> dict[str, object]:
        stats = bundle.global_stats
        if section_name == AnalysisDimensionName.TARGET_OVERVIEW:
            result = {
                "top_mesh_terms": stats.top_mesh_terms,
                "top_keywords": stats.top_keywords,
                "publication_type_distribution": stats.publication_type_distribution,
                "total_literature_count": stats.total_literature_count,
            }
        elif section_name == AnalysisDimensionName.PIPELINE_OVERVIEW:
            result = {
                "trial_phase_distribution": stats.trial_phase_distribution,
                "trial_status_distribution": stats.trial_status_distribution,
                "top_sponsors": stats.top_sponsors,
                "top_interventions": stats.top_interventions,
                "top_conditions": stats.top_conditions,
                "top_countries": stats.top_countries,
                "total_trial_count": stats.total_trial_count,
            }
        elif section_name == AnalysisDimensionName.RESEARCH_UPDATE:
            result = {
                "publication_count_by_year": stats.publication_count_by_year,
                "publication_type_distribution": stats.publication_type_distribution,
                "top_journals": stats.top_journals,
                "top_mesh_terms": stats.top_mesh_terms,
                "top_keywords": stats.top_keywords,
                "total_literature_count": stats.total_literature_count,
            }
        else:
            result = {
                "trial_phase_distribution": stats.trial_phase_distribution,
                "trial_status_distribution": stats.trial_status_distribution,
                "top_sponsors": stats.top_sponsors,
                "publication_count_by_year": stats.publication_count_by_year,
                "literature_with_nct_mentions_count": stats.literature_with_nct_mentions_count,
                "total_trial_count": stats.total_trial_count,
                "total_literature_count": stats.total_literature_count,
            }

        # The section generator sends this payload to the LLM as JSON.
        # Convert nested Pydantic value objects into plain JSON-safe data here,
        # so the prompt layer does not need to know about domain-model internals.
        return self._to_json_dict(result)

    def _append_missing_reference_warning(
        self,
        *,
        warnings: list[WarningItem],
        context_warnings: list[str],
        section_name: AnalysisDimensionName,
        source_type: ReportSourceType,
        record_key: str,
        message: str,
    ) -> None:
        warnings.append(
            WarningItem(
                code="report_context_reference_missing",
                level=WarningLevel.WARNING,
                scope=WarningScope.SECTION,
                message=message,
                related_ids=[section_name.value, record_key],
                details={
                    "section_name": section_name.value,
                    "source_type": source_type.value,
                    "record_key": record_key,
                },
            )
        )
        context_warnings.append(message)

    def _to_json_dict(self, values: dict[str, object]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values.items():
            result[key] = self._to_json_value(value)
        return result

    def _to_json_value(self, value: object) -> object:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [self._to_json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_json_value(item) for key, item in value.items()}
        return value
