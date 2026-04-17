"""Domain models."""

from app.domain.fetching import (
    ClinicalTrialsSourceConfig,
    ConnectorResult,
    FetchRun,
    FetchRunStatus,
    PubMedFilterConfig,
    PubMedSourceConfig,
    QuerySourceConfigs,
    RawRecord,
    SourceFetchSummary,
    SourceName,
    TargetQuery,
)

__all__ = [
    "ClinicalTrialsSourceConfig",
    "ConnectorResult",
    "FetchRun",
    "FetchRunStatus",
    "PubMedFilterConfig",
    "PubMedSourceConfig",
    "QuerySourceConfigs",
    "RawRecord",
    "SourceFetchSummary",
    "SourceName",
    "TargetQuery",
]
