from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class SourceName(str, Enum):
    CLINICALTRIALS = "clinicaltrials"
    PUBMED = "pubmed"


class FetchRunStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class PubMedFilterConfig(BaseModel):
    publication_types: list[str] = Field(default_factory=list)
    journals: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)
    title_abstract_terms: list[str] = Field(default_factory=list)
    extra_terms: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None
    has_abstract: bool | None = None


class ClinicalTrialsSourceConfig(BaseModel):
    enabled: bool = True
    page_size: int = 20
    max_pages: int = 1
    count_total: bool = True
    query: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    fields: list[str] = Field(default_factory=list)
    sort: str | list[str] | None = None

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, value: int) -> int:
        return min(max(value, 1), 100)

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, value: int) -> int:
        return min(max(value, 1), 10)


class PubMedSourceConfig(BaseModel):
    enabled: bool = True
    retmax: int = 20
    retstart: int = 0
    batch_size: int = 20
    sort: str = "pub_date"
    term: str | None = None
    filters: PubMedFilterConfig = Field(default_factory=PubMedFilterConfig)
    esearch_params: dict[str, Any] = Field(default_factory=dict)
    efetch_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("retmax")
    @classmethod
    def validate_retmax(cls, value: int) -> int:
        return min(max(value, 1), 100)

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, value: int) -> int:
        return min(max(value, 1), 100)


class QuerySourceConfigs(BaseModel):
    clinicaltrials: ClinicalTrialsSourceConfig = Field(
        default_factory=ClinicalTrialsSourceConfig
    )
    pubmed: PubMedSourceConfig = Field(default_factory=PubMedSourceConfig)


class TargetQuery(BaseModel):
    target: str
    indication: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_configs: QuerySourceConfigs = Field(default_factory=QuerySourceConfigs)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        target = value.strip()
        if not target:
            raise ValueError("target must not be empty")
        return target

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class RawRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    fetch_run_id: str
    source_name: SourceName
    source_id: str
    source_url: str | None = None
    target: str
    indication: str | None = None
    payload: dict[str, Any]
    query_snapshot: dict[str, Any]
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceFetchSummary(BaseModel):
    source_name: SourceName
    success: bool
    fetched_count: int
    total_count: int | None = None
    elapsed_ms: float
    warning: str | None = None
    request_snapshot: dict[str, Any] = Field(default_factory=dict)


class ConnectorResult(BaseModel):
    source_name: SourceName
    raw_records: list[RawRecord]
    total_count: int | None = None
    elapsed_ms: float
    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    warning: str | None = None


class FetchRun(BaseModel):
    fetch_run_id: str
    target: str
    indication: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_configs: dict[str, Any] = Field(default_factory=dict)
    status: FetchRunStatus = FetchRunStatus.PENDING
    raw_record_count: int = 0
    source_results: list[SourceFetchSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
