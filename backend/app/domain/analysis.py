from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.fetching import SourceName, TargetQuery


class DatePrecision(str, Enum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class WarningLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WarningScope(str, Enum):
    SOURCE = "source"
    RECORD = "record"
    SECTION = "section"
    BUNDLE = "bundle"


class SourceTrace(BaseModel):
    """Keeps a lossless pointer back to the raw record that produced a normalized entity."""

    raw_record_id: str
    fetch_run_id: str
    source_name: SourceName
    source_id: str
    source_url: str | None = None
    retrieved_at: datetime


class NormalizedDate(BaseModel):
    """Preserves both parsed value and original text because many source dates are partial."""

    raw_text: str | None = None
    value: date | None = None
    precision: DatePrecision | None = None


class AbstractSection(BaseModel):
    label: str | None = None
    text: str


class InterventionRef(BaseModel):
    name: str
    intervention_type: str | None = None
    other_names: list[str] = Field(default_factory=list)


class ArmGroupRef(BaseModel):
    label: str
    arm_type: str | None = None
    description: str | None = None
    intervention_names: list[str] = Field(default_factory=list)


class AuthorRef(BaseModel):
    collective_name: str | None = None
    last_name: str | None = None
    fore_name: str | None = None
    initials: str | None = None
    affiliations: list[str] = Field(default_factory=list)


class GrantRef(BaseModel):
    grant_id: str | None = None
    acronym: str | None = None
    agency: str | None = None
    country: str | None = None


class DatabankRef(BaseModel):
    name: str
    accession_numbers: list[str] = Field(default_factory=list)


class WarningItem(BaseModel):
    code: str
    level: WarningLevel
    scope: WarningScope
    message: str
    related_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class NamedCount(BaseModel):
    name: str
    count: int


class SponsorPhaseRow(BaseModel):
    sponsor: str
    phase_counts: dict[str, int] = Field(default_factory=dict)
    total_trials: int = 0


class CoverageSnapshot(BaseModel):
    """Summarizes whether each report-facing dimension has enough structured evidence."""

    has_trial_evidence: bool = False
    has_literature_evidence: bool = False
    has_target_overview_evidence: bool = False
    has_pipeline_overview_evidence: bool = False
    has_research_update_evidence: bool = False
    has_competition_assessment_evidence: bool = False
    missing_dimensions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GlobalAnalysisStats(BaseModel):
    """Stores reusable aggregate outputs that are not tied to a single report section."""

    total_trial_count: int = 0
    total_literature_count: int = 0
    trial_phase_distribution: dict[str, int] = Field(default_factory=dict)
    trial_status_distribution: dict[str, int] = Field(default_factory=dict)
    top_sponsors: list[NamedCount] = Field(default_factory=list)
    top_interventions: list[NamedCount] = Field(default_factory=list)
    top_conditions: list[NamedCount] = Field(default_factory=list)
    top_countries: list[NamedCount] = Field(default_factory=list)
    publication_count_by_year: dict[int, int] = Field(default_factory=dict)
    publication_type_distribution: dict[str, int] = Field(default_factory=dict)
    top_journals: list[NamedCount] = Field(default_factory=list)
    top_mesh_terms: list[NamedCount] = Field(default_factory=list)
    top_keywords: list[NamedCount] = Field(default_factory=list)
    literature_with_nct_mentions_count: int = 0


class NormalizedTrialRecord(BaseModel):
    """Stable cross-source trial representation used by normalization and downstream analysis."""

    trial_key: str = Field(default_factory=lambda: str(uuid4()))
    nct_id: str | None = None
    source_traces: list[SourceTrace] = Field(default_factory=list)
    brief_title: str | None = None
    official_title: str | None = None
    acronym: str | None = None
    summary: str | None = None
    study_type: str | None = None
    phase: str | None = None
    overall_status: str | None = None
    last_known_status: str | None = None
    lead_sponsor: str | None = None
    collaborators: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    browse_terms: list[str] = Field(default_factory=list)
    interventions: list[InterventionRef] = Field(default_factory=list)
    arm_groups: list[ArmGroupRef] = Field(default_factory=list)
    start_date: NormalizedDate | None = None
    primary_completion_date: NormalizedDate | None = None
    completion_date: NormalizedDate | None = None
    study_first_post_date: NormalizedDate | None = None
    last_update_post_date: NormalizedDate | None = None
    enrollment: int | None = None
    countries: list[str] = Field(default_factory=list)
    location_count: int | None = None
    has_results: bool | None = None
    primary_outcomes: list[str] = Field(default_factory=list)
    secondary_outcomes: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)


class NormalizedLiteratureRecord(BaseModel):
    """Normalized literature record keeps rich metadata because later analysis may need it."""

    literature_key: str = Field(default_factory=lambda: str(uuid4()))
    pmid: str | None = None
    doi: str | None = None
    source_traces: list[SourceTrace] = Field(default_factory=list)
    title: str | None = None
    journal: str | None = None
    publication_date: NormalizedDate | None = None
    publication_types: list[str] = Field(default_factory=list)
    abstract_sections: list[AbstractSection] = Field(default_factory=list)
    other_abstracts: list[AbstractSection] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)
    authors: list[AuthorRef] = Field(default_factory=list)
    affiliations: list[str] = Field(default_factory=list)
    grants: list[GrantRef] = Field(default_factory=list)
    databanks: list[DatabankRef] = Field(default_factory=list)
    linked_nct_ids: list[str] = Field(default_factory=list)
    related_pmids: list[str] = Field(default_factory=list)
    comments_corrections: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)


class TargetOverviewFacts(BaseModel):
    alias_terms: list[str] = Field(default_factory=list)
    disease_contexts: list[str] = Field(default_factory=list)
    top_mesh_terms: list[NamedCount] = Field(default_factory=list)
    top_keywords: list[NamedCount] = Field(default_factory=list)
    publication_type_distribution: dict[str, int] = Field(default_factory=dict)
    representative_paper_keys: list[str] = Field(default_factory=list)


class PipelineOverviewFacts(BaseModel):
    phase_distribution: dict[str, int] = Field(default_factory=dict)
    status_distribution: dict[str, int] = Field(default_factory=dict)
    top_sponsors: list[NamedCount] = Field(default_factory=list)
    top_interventions: list[NamedCount] = Field(default_factory=list)
    top_conditions: list[NamedCount] = Field(default_factory=list)
    country_distribution: list[NamedCount] = Field(default_factory=list)
    active_trial_count: int = 0
    results_posted_count: int = 0


class ResearchUpdateFacts(BaseModel):
    publication_count_by_year: dict[int, int] = Field(default_factory=dict)
    publication_type_distribution: dict[str, int] = Field(default_factory=dict)
    top_journals: list[NamedCount] = Field(default_factory=list)
    top_mesh_terms: list[NamedCount] = Field(default_factory=list)
    top_keywords: list[NamedCount] = Field(default_factory=list)
    recent_paper_keys: list[str] = Field(default_factory=list)
    high_value_paper_keys: list[str] = Field(default_factory=list)


class CompetitionAssessmentFacts(BaseModel):
    sponsor_phase_matrix: list[SponsorPhaseRow] = Field(default_factory=list)
    active_sponsor_count: int = 0
    late_stage_trial_count: int = 0
    recruiting_trial_count: int = 0
    results_posted_count: int = 0
    literature_with_nct_mentions_count: int = 0
    sponsor_concentration: list[NamedCount] = Field(default_factory=list)


class BaseSectionInput(BaseModel):
    """
    Section inputs keep stable references instead of copied excerpts.

    This keeps the bundle compact and avoids a second layer of partially duplicated text
    before we have finalized how excerpt-level evidence should be represented.
    """

    trial_keys: list[str] = Field(default_factory=list)
    literature_keys: list[str] = Field(default_factory=list)
    selection_notes: list[str] = Field(default_factory=list)
    truncation_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TargetOverviewSectionInput(BaseSectionInput):
    section_name: Literal["target_overview"] = "target_overview"
    facts: TargetOverviewFacts = Field(default_factory=TargetOverviewFacts)


class PipelineOverviewSectionInput(BaseSectionInput):
    section_name: Literal["pipeline_overview"] = "pipeline_overview"
    facts: PipelineOverviewFacts = Field(default_factory=PipelineOverviewFacts)


class ResearchUpdateSectionInput(BaseSectionInput):
    section_name: Literal["research_update"] = "research_update"
    facts: ResearchUpdateFacts = Field(default_factory=ResearchUpdateFacts)


class CompetitionAssessmentSectionInput(BaseSectionInput):
    section_name: Literal["competition_assessment"] = "competition_assessment"
    facts: CompetitionAssessmentFacts = Field(default_factory=CompetitionAssessmentFacts)


class SectionInputBundle(BaseModel):
    target_overview: TargetOverviewSectionInput = Field(
        default_factory=TargetOverviewSectionInput
    )
    pipeline_overview: PipelineOverviewSectionInput = Field(
        default_factory=PipelineOverviewSectionInput
    )
    research_update: ResearchUpdateSectionInput = Field(
        default_factory=ResearchUpdateSectionInput
    )
    competition_assessment: CompetitionAssessmentSectionInput = Field(
        default_factory=CompetitionAssessmentSectionInput
    )


class AnalysisReadyBundle(BaseModel):
    """
    Canonical stage 2 output consumed by report generation.

    The bundle separates reusable global aggregates from section-specific inputs so later
    report generators can share one upstream contract without re-reading raw source payloads.
    """

    bundle_id: str = Field(default_factory=lambda: str(uuid4()))
    query: TargetQuery
    trials: list[NormalizedTrialRecord] = Field(default_factory=list)
    literature: list[NormalizedLiteratureRecord] = Field(default_factory=list)
    global_stats: GlobalAnalysisStats = Field(default_factory=GlobalAnalysisStats)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    section_inputs: SectionInputBundle = Field(default_factory=SectionInputBundle)
    warnings: list[WarningItem] = Field(default_factory=list)
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
