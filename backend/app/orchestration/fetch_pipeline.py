from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.connectors.clinicaltrials import ClinicalTrialsGovConnector
from app.connectors.pubmed import PubMedConnector
from app.domain import (
    FetchRun,
    FetchRunStatus,
    SourceFetchSummary,
    SourceName,
    TargetQuery,
)
from app.infra.exceptions import AppException
from app.infra.settings import Settings, get_settings
from app.repository import FetchRunRepository, RawRecordRepository

logger = logging.getLogger(__name__)


class FetchPipelineService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        connectors: list | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.fetch_run_repository = FetchRunRepository(session)
        self.raw_record_repository = RawRecordRepository(session)
        self.connectors = connectors or [
            ClinicalTrialsGovConnector(settings=self.settings),
            PubMedConnector(settings=self.settings),
        ]

    def execute(self, query: TargetQuery) -> FetchRun:
        fetch_run = self.fetch_run_repository.create(query)
        source_results: list[SourceFetchSummary] = []
        warnings: list[str] = []
        raw_record_count = 0
        successful_sources = 0
        enabled_sources = 0

        for connector in self.connectors:
            source_name = SourceName(connector.source_name)
            if not self._is_source_enabled(query, source_name):
                continue
            enabled_sources += 1

            try:
                result = connector.search(query, fetch_run_id=fetch_run.fetch_run_id)
                self.raw_record_repository.create_many(result.raw_records)
                successful_sources += 1
                raw_record_count += len(result.raw_records)
                source_results.append(
                    SourceFetchSummary(
                        source_name=source_name,
                        success=True,
                        fetched_count=len(result.raw_records),
                        total_count=result.total_count,
                        elapsed_ms=result.elapsed_ms,
                        warning=result.warning,
                        request_snapshot=result.request_snapshot,
                    )
                )
            except Exception as exc:
                warning = f"{source_name.value} fetch failed: {exc}"
                logger.exception("source_fetch_failed source=%s target=%s", source_name.value, query.target)
                warnings.append(warning)
                source_results.append(
                    SourceFetchSummary(
                        source_name=source_name,
                        success=False,
                        fetched_count=0,
                        total_count=None,
                        elapsed_ms=0,
                        warning=warning,
                        request_snapshot={},
                    )
                )

        if enabled_sources == 0:
            self.fetch_run_repository.update_summary(
                fetch_run.fetch_run_id,
                status=FetchRunStatus.FAILED.value,
                raw_record_count=0,
                source_results=[],
                warnings=["No source is enabled for this fetch request."],
            )
            raise AppException(
                "No source is enabled for this fetch request.",
                code="no_enabled_source",
                status_code=400,
                details={"fetch_run_id": fetch_run.fetch_run_id},
            )

        status = self._resolve_status(successful_sources, warnings)
        persisted_run = self.fetch_run_repository.update_summary(
            fetch_run.fetch_run_id,
            status=status.value,
            raw_record_count=raw_record_count,
            source_results=source_results,
            warnings=warnings,
        )

        if successful_sources == 0:
            raise AppException(
                "All enabled source fetches failed.",
                code="all_sources_failed",
                status_code=502,
                details={"fetch_run_id": fetch_run.fetch_run_id, "warnings": warnings},
            )

        return persisted_run

    def get_fetch_run(self, fetch_run_id: str) -> FetchRun:
        fetch_run = self.fetch_run_repository.get(fetch_run_id)
        if fetch_run is None:
            raise AppException(
                "Fetch run not found.",
                code="fetch_run_not_found",
                status_code=404,
                details={"fetch_run_id": fetch_run_id},
            )
        return fetch_run

    def list_raw_records(
        self,
        fetch_run_id: str,
        *,
        source_name: SourceName | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        self.get_fetch_run(fetch_run_id)
        return self.raw_record_repository.list_by_fetch_run(
            fetch_run_id,
            source_name=source_name,
            limit=limit,
            offset=offset,
        )

    def _is_source_enabled(self, query: TargetQuery, source_name: SourceName) -> bool:
        if source_name == SourceName.CLINICALTRIALS:
            return query.source_configs.clinicaltrials.enabled
        if source_name == SourceName.PUBMED:
            return query.source_configs.pubmed.enabled
        return False

    def _resolve_status(
        self,
        successful_sources: int,
        warnings: list[str],
    ) -> FetchRunStatus:
        if successful_sources == 0:
            return FetchRunStatus.FAILED
        if warnings:
            return FetchRunStatus.PARTIAL_FAILURE
        return FetchRunStatus.COMPLETED
