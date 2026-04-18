from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.clinicaltrials.client import ClinicalTrialsGovClient
from app.domain import ConnectorResult, RawRecord, SourceName, TargetQuery


class ClinicalTrialsGovConnector(BaseConnector):
    source_name = SourceName.CLINICALTRIALS

    def __init__(
        self,
        *,
        sleep_fn: Callable[[float], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.client = ClinicalTrialsGovClient(self.settings)
        self.sleep_fn = sleep_fn or time.sleep

    def search(self, query: TargetQuery, *, fetch_run_id: str) -> ConnectorResult:
        config = query.source_configs.clinicaltrials
        params = self._build_search_params(query)
        record_cap = self.settings.fetch_clinicaltrials_max_records
        query_interval_seconds = self.settings.fetch_query_interval_seconds
        raw_records: list[RawRecord] = []
        page_snapshots: list[dict[str, Any]] = []
        next_page_token: str | None = None
        total_count: int | None = None
        stop_reason = "empty_page"
        page_index = 0

        started = time.perf_counter()
        with self.client_context() as http_client:
            # `page_size` controls the per-request batch size. The env-level cap
            # controls when we stop paginating, and we intentionally allow the
            # last page to overshoot that cap instead of truncating results.
            while True:
                if page_index > 0 and query_interval_seconds > 0:
                    self.sleep_fn(query_interval_seconds)

                page_params = dict(params)
                if next_page_token:
                    page_params["pageToken"] = next_page_token

                response = self.client.search_studies(http_client, page_params)
                payload = response.json()
                studies = payload.get("studies", [])
                next_page_token = payload.get("nextPageToken")
                if total_count is None:
                    total_count = self._extract_total_count(payload)

                request_snapshot = {
                    "page_index": page_index,
                    "params": page_params,
                    "returned_count": len(studies),
                    "next_page_token": next_page_token,
                }
                page_snapshots.append(request_snapshot)

                if not studies:
                    stop_reason = "empty_page"
                    break

                for study_index, study in enumerate(studies):
                    source_id = self._extract_source_id(study, study_index, page_index)
                    raw_records.append(
                        RawRecord(
                            fetch_run_id=fetch_run_id,
                            source_name=self.source_name,
                            source_id=source_id,
                            source_url=f"https://clinicaltrials.gov/study/{source_id}",
                            target=query.target,
                            indication=query.indication,
                            payload=study,
                            query_snapshot=request_snapshot,
                        )
                    )

                if len(raw_records) >= record_cap:
                    stop_reason = "record_cap_reached"
                    break
                if not next_page_token:
                    stop_reason = "no_next_page_token"
                    break
                page_index += 1

        elapsed_ms = (time.perf_counter() - started) * 1000
        return ConnectorResult(
            source_name=self.source_name,
            raw_records=raw_records,
            total_count=total_count,
            elapsed_ms=elapsed_ms,
            request_snapshot={
                "params": params,
                "pages": page_snapshots,
                "applied_record_cap": record_cap,
                "stop_reason": stop_reason,
                "next_page_token": next_page_token,
            },
        )

    def _build_search_params(self, query: TargetQuery) -> dict[str, str]:
        config = query.source_configs.clinicaltrials
        params: dict[str, str] = {
            "format": "json",
            "pageSize": str(config.page_size),
            "countTotal": "true" if config.count_total else "false",
        }
        if config.fields:
            params["fields"] = ",".join(config.fields)

        if config.sort:
            params["sort"] = self._serialize_value(config.sort)

        for key, value in config.query.items():
            actual_key = key if key.startswith("query.") else f"query.{key}"
            params[actual_key] = self._serialize_value(value)

        for key, value in config.filters.items():
            actual_key = key if key.startswith("filter.") else f"filter.{key}"
            params[actual_key] = self._serialize_value(value)

        if "query.term" not in params:
            params["query.term"] = self._build_target_expression(query)
        if query.indication and "query.cond" not in params:
            params["query.cond"] = query.indication

        return params

    def _build_target_expression(self, query: TargetQuery) -> str:
        terms = [query.target, *query.aliases]
        unique_terms = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
        if len(unique_terms) == 1:
            return unique_terms[0]
        return " OR ".join(unique_terms)

    def _extract_source_id(self, study: dict[str, Any], study_index: int, page_index: int) -> str:
        identification_module = (
            study.get("protocolSection", {}).get("identificationModule", {})
        )
        nct_id = identification_module.get("nctId")
        return nct_id or f"clinicaltrials-{page_index}-{study_index}"

    def _extract_total_count(self, payload: dict[str, Any]) -> int | None:
        for key in ("totalCount", "total_count"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None

    def _serialize_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)

