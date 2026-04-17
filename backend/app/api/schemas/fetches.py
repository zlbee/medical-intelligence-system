from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain import QuerySourceConfigs, SourceFetchSummary, SourceName, TargetQuery


class FetchCreateRequest(BaseModel):
    target: str
    indication: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_configs: QuerySourceConfigs = Field(default_factory=QuerySourceConfigs)

    def to_target_query(self) -> TargetQuery:
        return TargetQuery(
            target=self.target,
            indication=self.indication,
            aliases=self.aliases,
            source_configs=self.source_configs,
        )


class FetchRunResponse(BaseModel):
    fetch_run_id: str
    target: str
    indication: str | None = None
    aliases: list[str] = Field(default_factory=list)
    status: str
    raw_record_count: int
    source_results: list[SourceFetchSummary]
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class RawRecordResponse(BaseModel):
    record_id: str
    fetch_run_id: str
    source_name: SourceName
    source_id: str
    source_url: str | None = None
    target: str
    indication: str | None = None
    payload: dict[str, Any]
    query_snapshot: dict[str, Any]
    retrieved_at: datetime


class RawRecordListResponse(BaseModel):
    fetch_run_id: str
    total_items: int
    limit: int
    offset: int
    items: list[RawRecordResponse]

