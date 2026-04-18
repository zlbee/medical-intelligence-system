from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.domain.analysis import (
    AnalysisDimensionName,
    LiteratureLLMEnrichment,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    TrialLLMEnrichment,
    WarningItem,
)
from app.domain.fetching import TargetQuery


SECTION_TITLES = {
    AnalysisDimensionName.TARGET_OVERVIEW: "靶点概述",
    AnalysisDimensionName.PIPELINE_OVERVIEW: "在研管线概览",
    AnalysisDimensionName.RESEARCH_UPDATE: "近期研究动态",
    AnalysisDimensionName.COMPETITION_ASSESSMENT: "竞争格局判断",
}


class ReportSourceType(str, Enum):
    TRIAL = "trial"
    LITERATURE = "literature"


class ReportWarningSummary(BaseModel):
    code: str
    message: str
    count: int


class GeneratedSectionDraft(BaseModel):
    """
    Structured LLM output for one report section.

    The draft is intentionally small and citation-focused so the orchestration layer can
    validate referenced keys before the section becomes part of the persisted report.
    """

    title: str
    summary: str
    markdown_body: str
    key_takeaways: list[str] = Field(default_factory=list)
    trial_keys: list[str] = Field(default_factory=list)
    literature_keys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("trial_keys", "literature_keys")
    @classmethod
    def normalize_key_lists(cls, values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            key = value.strip()
            if not key or key in deduped:
                continue
            deduped.append(key)
        return deduped

    @field_validator("key_takeaways")
    @classmethod
    def normalize_key_takeaways(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = value.strip()
            if not item or item in cleaned:
                continue
            cleaned.append(item)
        return cleaned[:6]


class SectionGenerationContext(BaseModel):
    """Database-backed input envelope for a single report section generation call."""

    fetch_run_id: str
    analysis_bundle_id: str
    section_name: AnalysisDimensionName
    title: str
    query: TargetQuery
    facts: dict[str, Any] = Field(default_factory=dict)
    global_stats: dict[str, Any] = Field(default_factory=dict)
    selection_notes: list[str] = Field(default_factory=list)
    truncation_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    trials: list[NormalizedTrialRecord] = Field(default_factory=list)
    literature: list[NormalizedLiteratureRecord] = Field(default_factory=list)
    trial_enrichments: list[TrialLLMEnrichment] = Field(default_factory=list)
    literature_enrichments: list[LiteratureLLMEnrichment] = Field(default_factory=list)


class ReportSection(BaseModel):
    section_name: AnalysisDimensionName
    title: str
    summary: str
    markdown_body: str
    key_takeaways: list[str] = Field(default_factory=list)
    trial_keys: list[str] = Field(default_factory=list)
    literature_keys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportSourceRef(BaseModel):
    report_id: str
    fetch_run_id: str
    section_name: AnalysisDimensionName
    source_type: ReportSourceType
    record_key: str
    source_id: str
    display_title: str
    source_url: str | None = None
    display_order: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportDocument(BaseModel):
    report_id: str = Field(default_factory=lambda: str(uuid4()))
    fetch_run_id: str
    analysis_bundle_id: str
    target: str
    indication: str | None = None
    markdown_content: str
    sections: list[ReportSection] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    warning_summary: list[ReportWarningSummary] = Field(default_factory=list)
    source_refs: list[ReportSourceRef] = Field(default_factory=list)
    model: str | None = None
    prompt_versions: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
