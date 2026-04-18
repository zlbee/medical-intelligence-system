from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain import AnalysisReadyBundle, WarningItem


class QuerySummaryResponse(BaseModel):
    target: str
    indication: str | None = None
    aliases: list[str] = Field(default_factory=list)


class NamedCountResponse(BaseModel):
    name: str
    count: int


class SponsorPhaseRowResponse(BaseModel):
    sponsor: str
    phase_counts: dict[str, int] = Field(default_factory=dict)
    total_trials: int


class WarningItemResponse(BaseModel):
    code: str
    level: str
    scope: str
    message: str
    related_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, warning: WarningItem) -> "WarningItemResponse":
        return cls(
            code=warning.code,
            level=warning.level.value,
            scope=warning.scope.value,
            message=warning.message,
            related_ids=warning.related_ids,
            details=warning.details,
        )


class CoverageSnapshotResponse(BaseModel):
    has_trial_evidence: bool
    has_literature_evidence: bool
    has_target_overview_evidence: bool
    has_pipeline_overview_evidence: bool
    has_research_update_evidence: bool
    has_competition_assessment_evidence: bool
    missing_dimensions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class LLMEnrichmentSummaryResponse(BaseModel):
    trial_total: int
    trial_succeeded: int
    literature_total: int
    literature_succeeded: int
    warning_count: int
    model: str | None = None
    prompt_versions: list[str] = Field(default_factory=list)


class GlobalAnalysisStatsResponse(BaseModel):
    total_trial_count: int
    total_literature_count: int
    trial_phase_distribution: dict[str, int] = Field(default_factory=dict)
    trial_status_distribution: dict[str, int] = Field(default_factory=dict)
    top_sponsors: list[NamedCountResponse] = Field(default_factory=list)
    top_interventions: list[NamedCountResponse] = Field(default_factory=list)
    top_conditions: list[NamedCountResponse] = Field(default_factory=list)
    top_countries: list[NamedCountResponse] = Field(default_factory=list)
    publication_count_by_year: dict[int, int] = Field(default_factory=dict)
    publication_type_distribution: dict[str, int] = Field(default_factory=dict)
    top_journals: list[NamedCountResponse] = Field(default_factory=list)
    top_mesh_terms: list[NamedCountResponse] = Field(default_factory=list)
    top_keywords: list[NamedCountResponse] = Field(default_factory=list)
    literature_with_nct_mentions_count: int


class SectionInputResponse(BaseModel):
    section_name: str
    trial_keys: list[str] = Field(default_factory=list)
    literature_keys: list[str] = Field(default_factory=list)
    selection_notes: list[str] = Field(default_factory=list)
    truncation_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)


class SectionInputBundleResponse(BaseModel):
    target_overview: SectionInputResponse
    pipeline_overview: SectionInputResponse
    research_update: SectionInputResponse
    competition_assessment: SectionInputResponse


class AnalysisBundleResponse(BaseModel):
    fetch_run_id: str
    bundle_id: str
    query: QuerySummaryResponse
    global_stats: GlobalAnalysisStatsResponse
    coverage: CoverageSnapshotResponse
    section_inputs: SectionInputBundleResponse
    llm_enrichment_summary: LLMEnrichmentSummaryResponse
    warnings: list[WarningItemResponse] = Field(default_factory=list)
    built_at: datetime

    @classmethod
    def from_domain(
        cls,
        *,
        fetch_run_id: str,
        bundle: AnalysisReadyBundle,
    ) -> "AnalysisBundleResponse":
        # The API intentionally returns a report-focused view instead of the entire
        # bundle payload so the frontend can inspect stage-2 outputs without
        # downloading every normalized record.
        return cls(
            fetch_run_id=fetch_run_id,
            bundle_id=bundle.bundle_id,
            query=QuerySummaryResponse(
                target=bundle.query.target,
                indication=bundle.query.indication,
                aliases=bundle.query.aliases,
            ),
            global_stats=GlobalAnalysisStatsResponse.model_validate(
                bundle.global_stats.model_dump(mode="json")
            ),
            coverage=CoverageSnapshotResponse.model_validate(
                bundle.coverage.model_dump(mode="json")
            ),
            section_inputs=SectionInputBundleResponse(
                target_overview=_to_section_input_response(bundle.section_inputs.target_overview),
                pipeline_overview=_to_section_input_response(bundle.section_inputs.pipeline_overview),
                research_update=_to_section_input_response(bundle.section_inputs.research_update),
                competition_assessment=_to_section_input_response(
                    bundle.section_inputs.competition_assessment
                ),
            ),
            llm_enrichment_summary=LLMEnrichmentSummaryResponse.model_validate(
                bundle.llm_enrichment_summary.model_dump(mode="json")
            ),
            warnings=[WarningItemResponse.from_domain(item) for item in bundle.warnings],
            built_at=bundle.built_at,
        )


def _to_section_input_response(section) -> SectionInputResponse:
    return SectionInputResponse(
        section_name=section.section_name,
        trial_keys=section.trial_keys,
        literature_keys=section.literature_keys,
        selection_notes=section.selection_notes,
        truncation_notes=section.truncation_notes,
        warnings=section.warnings,
        facts=section.facts.model_dump(mode="json"),
    )
