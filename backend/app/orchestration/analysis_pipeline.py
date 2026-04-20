from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.analyze import (
    AnalysisBundleBuilder,
    LiteratureLLMEnhancementService,
    SectionSelector,
    TrialLLMEnhancementService,
)
from app.analyze.scoring import build_literature_rule_scores, build_trial_rule_scores
from app.domain import (
    AnalysisReadyBundle,
    LiteratureLLMEnrichment,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    RawRecord,
    RuleScoreBreakdown,
    SourceName,
    TargetQuery,
    TrialLLMEnrichment,
    WarningItem,
    WarningLevel,
    WarningScope,
)
from app.infra.exceptions import AppException
from app.llm import LLMClient
from app.normalize import LiteratureNormalizer, TrialNormalizer
from app.repository import (
    AnalysisSnapshotRepository,
    FetchRunRepository,
    LiteratureLLMEnrichmentRepository,
    NormalizedLiteratureRecordRepository,
    NormalizedTrialRecordRepository,
    RawRecordRepository,
    TrialLLMEnrichmentRepository,
)

SELECTOR_CANDIDATE_POOL_MULTIPLIER = 2


@dataclass(slots=True)
class _LLMEnrichmentResult:
    trial_enrichments: list[TrialLLMEnrichment]
    literature_enrichments: list[LiteratureLLMEnrichment]
    warnings: list[WarningItem]
    selector_trials: list[NormalizedTrialRecord] | None = None
    selector_literature: list[NormalizedLiteratureRecord] | None = None


class AnalysisPipelineService:
    """Runs stage 2 from persisted raw records to a reusable analysis snapshot."""

    def __init__(
        self,
        session: Session,
        *,
        llm_client: LLMClient | None = None,
        llm_model: str | None = None,
        llm_enrichment_full_scan: bool = True,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.llm_enrichment_full_scan = llm_enrichment_full_scan
        self.fetch_run_repository = FetchRunRepository(session)
        self.raw_record_repository = RawRecordRepository(session)
        self.normalized_trial_record_repository = NormalizedTrialRecordRepository(session)
        self.normalized_literature_record_repository = NormalizedLiteratureRecordRepository(
            session
        )
        self.trial_llm_enrichment_repository = TrialLLMEnrichmentRepository(session)
        self.literature_llm_enrichment_repository = LiteratureLLMEnrichmentRepository(session)
        self.analysis_snapshot_repository = AnalysisSnapshotRepository(session)
        self.trial_normalizer = TrialNormalizer()
        self.literature_normalizer = LiteratureNormalizer()
        self.bundle_builder = AnalysisBundleBuilder()
        self.trial_enhancement_service = (
            TrialLLMEnhancementService(llm_client, model=llm_model)
            if llm_client is not None
            else None
        )
        self.literature_enhancement_service = (
            LiteratureLLMEnhancementService(llm_client, model=llm_model)
            if llm_client is not None
            else None
        )

    def build(self, fetch_run_id: str) -> AnalysisReadyBundle:
        fetch_run = self.fetch_run_repository.get(fetch_run_id)
        if fetch_run is None:
            raise AppException(
                "Fetch run not found.",
                code="fetch_run_not_found",
                status_code=404,
                details={"fetch_run_id": fetch_run_id},
            )

        raw_records = self.raw_record_repository.list_all_by_fetch_run(fetch_run_id)
        if not raw_records:
            raise AppException(
                "No raw records found for the fetch run.",
                code="raw_records_not_found",
                status_code=400,
                details={"fetch_run_id": fetch_run_id},
            )

        query = self._to_target_query(fetch_run)
        trials = self._build_normalized_trials(raw_records)
        literature = self._build_normalized_literature(raw_records)

        self.normalized_trial_record_repository.replace_for_fetch_run(fetch_run_id, trials)
        self.normalized_literature_record_repository.replace_for_fetch_run(
            fetch_run_id,
            literature,
        )

        trial_rule_scores = {
            record.trial_key: build_trial_rule_scores(query, record) for record in trials
        }
        literature_rule_scores = {
            record.literature_key: build_literature_rule_scores(query, record)
            for record in literature
        }
        llm_result = self._build_llm_enrichments(
            fetch_run_id=fetch_run_id,
            query=query,
            trial_rule_scores=trial_rule_scores,
            literature_rule_scores=literature_rule_scores,
            trials=trials,
            literature=literature,
        )

        self.trial_llm_enrichment_repository.replace_for_fetch_run(
            fetch_run_id,
            llm_result.trial_enrichments,
        )
        self.literature_llm_enrichment_repository.replace_for_fetch_run(
            fetch_run_id,
            llm_result.literature_enrichments,
        )

        bundle = self.bundle_builder.build(
            query=query,
            trials=trials,
            literature=literature,
            selector_trials=llm_result.selector_trials,
            selector_literature=llm_result.selector_literature,
            trial_llm_enrichments=llm_result.trial_enrichments,
            literature_llm_enrichments=llm_result.literature_enrichments,
            llm_warnings=llm_result.warnings,
        )
        return self.analysis_snapshot_repository.upsert(fetch_run_id, bundle)

    def get_bundle(self, fetch_run_id: str) -> AnalysisReadyBundle:
        bundle = self.analysis_snapshot_repository.get(fetch_run_id)
        if bundle is None:
            raise AppException(
                "Analysis snapshot not found.",
                code="analysis_snapshot_not_found",
                status_code=404,
                details={"fetch_run_id": fetch_run_id},
            )
        return bundle

    def list_normalized_trials(self, fetch_run_id: str):
        self._ensure_fetch_run(fetch_run_id)
        return self.normalized_trial_record_repository.list_by_fetch_run(fetch_run_id)

    def list_normalized_literature(self, fetch_run_id: str):
        self._ensure_fetch_run(fetch_run_id)
        return self.normalized_literature_record_repository.list_by_fetch_run(fetch_run_id)

    def _build_llm_enrichments(
        self,
        *,
        fetch_run_id: str,
        query: TargetQuery,
        trial_rule_scores: dict[str, RuleScoreBreakdown],
        literature_rule_scores: dict[str, RuleScoreBreakdown],
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
    ) -> _LLMEnrichmentResult:
        warnings: list[WarningItem] = []
        trial_enrichment_map = self.trial_llm_enrichment_repository.find_latest_by_trial_keys(
            [record.trial_key for record in trials]
        )
        literature_enrichment_map = (
            self.literature_llm_enrichment_repository.find_latest_by_literature_keys(
                [record.literature_key for record in literature]
            )
        )
        selected_trials, selected_literature = self._select_llm_candidates(
            query=query,
            trials=trials,
            literature=literature,
            trial_enrichments_by_key=trial_enrichment_map,
            literature_enrichments_by_key=literature_enrichment_map,
        )
        selector_trials = None if self.llm_enrichment_full_scan else selected_trials
        selector_literature = None if self.llm_enrichment_full_scan else selected_literature
        trial_enrichments = [
            self._clone_trial_enrichment_for_fetch(
                fetch_run_id=fetch_run_id,
                enrichment=trial_enrichment_map[record.trial_key],
            )
            for record in selected_trials
            if record.trial_key in trial_enrichment_map
        ]
        literature_enrichments = [
            self._clone_literature_enrichment_for_fetch(
                fetch_run_id=fetch_run_id,
                enrichment=literature_enrichment_map[record.literature_key],
            )
            for record in selected_literature
            if record.literature_key in literature_enrichment_map
        ]
        cached_trial_keys = {record.trial_key for record in trial_enrichments}
        cached_literature_keys = {record.literature_key for record in literature_enrichments}

        if not self.llm_enrichment_full_scan:
            warnings.extend(
                self._build_selector_pool_warning(
                    trial_candidates=selected_trials,
                    literature_candidates=selected_literature,
                    total_trial_count=len(trials),
                    total_literature_count=len(literature),
                )
            )

        if self.llm_client is None or self.trial_enhancement_service is None:
            warnings.append(
                WarningItem(
                    code="llm_enrichment_disabled",
                    level=WarningLevel.WARNING,
                    scope=WarningScope.BUNDLE,
                    message=(
                        "LLM enrichment is not configured; cached enrichments are reused "
                        "where available and remaining records continue with rule-score fallback."
                    ),
                    details={"model": self.llm_model},
                )
            )
            return _LLMEnrichmentResult(
                trial_enrichments=trial_enrichments,
                literature_enrichments=literature_enrichments,
                warnings=warnings,
                selector_trials=selector_trials,
                selector_literature=selector_literature,
            )

        for trial in selected_trials:
            if trial.trial_key in cached_trial_keys:
                continue
            try:
                trial_enrichments.append(
                    self.trial_enhancement_service.enhance(
                        fetch_run_id=fetch_run_id,
                        query=query,
                        trial=trial,
                        rule_scores=trial_rule_scores[trial.trial_key],
                    )
                )
            except Exception as exc:  # noqa: BLE001 - best-effort policy is deliberate here.
                warnings.append(
                    self._build_llm_record_warning(
                        code="trial_llm_enrichment_failed",
                        record_id=trial.trial_key,
                        source_name=SourceName.CLINICALTRIALS.value,
                        exc=exc,
                    )
                )

        if self.literature_enhancement_service is None:
            return _LLMEnrichmentResult(
                trial_enrichments=trial_enrichments,
                literature_enrichments=literature_enrichments,
                warnings=warnings,
                selector_trials=selector_trials,
                selector_literature=selector_literature,
            )
        for paper in selected_literature:
            if paper.literature_key in cached_literature_keys:
                continue
            try:
                literature_enrichments.append(
                    self.literature_enhancement_service.enhance(
                        fetch_run_id=fetch_run_id,
                        query=query,
                        literature=paper,
                        rule_scores=literature_rule_scores[paper.literature_key],
                    )
                )
            except Exception as exc:  # noqa: BLE001 - best-effort policy is deliberate here.
                warnings.append(
                    self._build_llm_record_warning(
                        code="literature_llm_enrichment_failed",
                        record_id=paper.literature_key,
                        source_name=SourceName.PUBMED.value,
                        exc=exc,
                    )
                )
        return _LLMEnrichmentResult(
            trial_enrichments=trial_enrichments,
            literature_enrichments=literature_enrichments,
            warnings=warnings,
            selector_trials=selector_trials,
            selector_literature=selector_literature,
        )

    def _select_llm_candidates(
        self,
        *,
        query: TargetQuery,
        trials: list[NormalizedTrialRecord],
        literature: list[NormalizedLiteratureRecord],
        trial_enrichments_by_key: dict[str, TrialLLMEnrichment],
        literature_enrichments_by_key: dict[str, LiteratureLLMEnrichment],
    ) -> tuple[list[NormalizedTrialRecord], list[NormalizedLiteratureRecord]]:
        if self.llm_enrichment_full_scan:
            return trials, literature

        selector = self._build_candidate_pool_selector()
        target_selection = selector.select_target_overview(
            query,
            trials,
            literature,
            trial_enrichments_by_key=trial_enrichments_by_key,
            literature_enrichments_by_key=literature_enrichments_by_key,
        )
        pipeline_selection = selector.select_pipeline_overview(
            query,
            trials,
            trial_enrichments_by_key=trial_enrichments_by_key,
        )
        research_selection = selector.select_research_update(
            query,
            literature,
            literature_enrichments_by_key=literature_enrichments_by_key,
        )
        competition_selection = selector.select_competition_assessment(
            query,
            trials,
            literature,
            trial_enrichments_by_key=trial_enrichments_by_key,
            literature_enrichments_by_key=literature_enrichments_by_key,
        )
        trial_map = {record.trial_key: record for record in trials}
        literature_map = {record.literature_key: record for record in literature}
        trial_keys = self._unique_keys(
            [
                *target_selection.trial_keys,
                *pipeline_selection.trial_keys,
                *competition_selection.trial_keys,
            ]
        )
        literature_keys = self._unique_keys(
            [
                *target_selection.literature_keys,
                *research_selection.literature_keys,
                *competition_selection.literature_keys,
            ]
        )
        return (
            [trial_map[key] for key in trial_keys if key in trial_map],
            [literature_map[key] for key in literature_keys if key in literature_map],
        )

    def _build_candidate_pool_selector(self) -> SectionSelector:
        base_selector = self.bundle_builder.selector
        multiplier = SELECTOR_CANDIDATE_POOL_MULTIPLIER
        return SectionSelector(
            target_overview_literature_limit=(
                base_selector.target_overview_literature_limit * multiplier
            ),
            target_overview_trial_limit=(
                base_selector.target_overview_trial_limit * multiplier
            ),
            pipeline_trial_limit=base_selector.pipeline_trial_limit * multiplier,
            research_recent_limit=base_selector.research_recent_limit * multiplier,
            research_high_value_limit=base_selector.research_high_value_limit * multiplier,
            competition_trial_limit=base_selector.competition_trial_limit * multiplier,
            competition_literature_limit=(
                base_selector.competition_literature_limit * multiplier
            ),
        )

    def _build_selector_pool_warning(
        self,
        *,
        trial_candidates: list[NormalizedTrialRecord],
        literature_candidates: list[NormalizedLiteratureRecord],
        total_trial_count: int,
        total_literature_count: int,
    ) -> list[WarningItem]:
        warnings: list[WarningItem] = []
        if (
            len(trial_candidates) < total_trial_count
            or len(literature_candidates) < total_literature_count
        ):
            # The selector pool keeps LLM spending aligned with report sections while
            # preserving full-record stats in the final analysis bundle.
            warnings.append(
                WarningItem(
                    code="llm_enrichment_selector_pool_applied",
                    level=WarningLevel.WARNING,
                    scope=WarningScope.BUNDLE,
                    message=(
                        "Selector-pool LLM enrichment is enabled; new LLM generation "
                        "only runs for section candidate records."
                    ),
                    details={
                        "candidate_pool_multiplier": SELECTOR_CANDIDATE_POOL_MULTIPLIER,
                        "trial_candidates": len(trial_candidates),
                        "total_trial_count": total_trial_count,
                        "literature_candidates": len(literature_candidates),
                        "total_literature_count": total_literature_count,
                    },
                )
            )
        return warnings

    def _unique_keys(self, keys: list[str]) -> list[str]:
        return list(dict.fromkeys(keys))

    def _build_normalized_trials(
        self,
        raw_records: list[RawRecord],
    ) -> list[NormalizedTrialRecord]:
        grouped_records = self._group_trial_records_by_key(raw_records)
        cached_records = self.normalized_trial_record_repository.find_latest_by_trial_keys(
            list(grouped_records.keys())
        )
        normalized_records: list[NormalizedTrialRecord] = []
        for trial_key, records in grouped_records.items():
            cached = cached_records.get(trial_key)
            if cached is not None:
                normalized_records.append(
                    self._clone_trial_record_for_fetch(
                        cached_record=cached,
                        raw_records=records,
                    )
                )
                continue
            normalized_records.extend(self.trial_normalizer.normalize_many(records))
        return normalized_records

    def _build_normalized_literature(
        self,
        raw_records: list[RawRecord],
    ) -> list[NormalizedLiteratureRecord]:
        grouped_records = self._group_literature_records_by_key(raw_records)
        cached_records = (
            self.normalized_literature_record_repository.find_latest_by_literature_keys(
                list(grouped_records.keys())
            )
        )
        normalized_records: list[NormalizedLiteratureRecord] = []
        for literature_key, records in grouped_records.items():
            cached = cached_records.get(literature_key)
            if cached is not None:
                normalized_records.append(
                    self._clone_literature_record_for_fetch(
                        cached_record=cached,
                        raw_records=records,
                    )
                )
                continue
            normalized_records.extend(self.literature_normalizer.normalize_many(records))
        return normalized_records

    def _group_trial_records_by_key(
        self,
        raw_records: list[RawRecord],
    ) -> dict[str, list[RawRecord]]:
        grouped: dict[str, list[RawRecord]] = {}
        for record in raw_records:
            if record.source_name != SourceName.CLINICALTRIALS:
                continue
            trial_key = self.trial_normalizer.extract_trial_key(record)
            grouped.setdefault(trial_key, []).append(record)
        return grouped

    def _group_literature_records_by_key(
        self,
        raw_records: list[RawRecord],
    ) -> dict[str, list[RawRecord]]:
        grouped: dict[str, list[RawRecord]] = {}
        for record in raw_records:
            if record.source_name != SourceName.PUBMED:
                continue
            literature_key = self.literature_normalizer.extract_literature_key(record)
            grouped.setdefault(literature_key, []).append(record)
        return grouped

    def _clone_trial_record_for_fetch(
        self,
        *,
        cached_record: NormalizedTrialRecord,
        raw_records: list[RawRecord],
    ) -> NormalizedTrialRecord:
        cloned = cached_record.model_copy(deep=True)
        # Cross-fetch cache reuse should preserve the stable normalized business fields,
        # but tracing must always point at the raw records that participated in the
        # current fetch run so downstream debugging and source display stay correct.
        cloned.source_traces = [
            self.trial_normalizer.build_source_trace(record) for record in raw_records
        ]
        return cloned

    def _clone_literature_record_for_fetch(
        self,
        *,
        cached_record: NormalizedLiteratureRecord,
        raw_records: list[RawRecord],
    ) -> NormalizedLiteratureRecord:
        cloned = cached_record.model_copy(deep=True)
        cloned.source_traces = [
            self.literature_normalizer.build_source_trace(record) for record in raw_records
        ]
        return cloned

    def _clone_trial_enrichment_for_fetch(
        self,
        *,
        fetch_run_id: str,
        enrichment: TrialLLMEnrichment,
    ) -> TrialLLMEnrichment:
        return enrichment.model_copy(update={"fetch_run_id": fetch_run_id}, deep=True)

    def _clone_literature_enrichment_for_fetch(
        self,
        *,
        fetch_run_id: str,
        enrichment: LiteratureLLMEnrichment,
    ) -> LiteratureLLMEnrichment:
        return enrichment.model_copy(update={"fetch_run_id": fetch_run_id}, deep=True)

    def _build_llm_record_warning(
        self,
        *,
        code: str,
        record_id: str,
        source_name: str,
        exc: Exception,
    ) -> WarningItem:
        return WarningItem(
            code=code,
            level=WarningLevel.WARNING,
            scope=WarningScope.RECORD,
            message=(
                "LLM enrichment failed for one record; rule-score fallback will be used "
                "for downstream ranking."
            ),
            related_ids=[record_id],
            details={
                "record_id": record_id,
                "source_name": source_name,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )

    def _ensure_fetch_run(self, fetch_run_id: str) -> None:
        if self.fetch_run_repository.get(fetch_run_id) is None:
            raise AppException(
                "Fetch run not found.",
                code="fetch_run_not_found",
                status_code=404,
                details={"fetch_run_id": fetch_run_id},
            )

    def _to_target_query(self, fetch_run) -> TargetQuery:
        return TargetQuery(
            target=fetch_run.target,
            indication=fetch_run.indication,
            aliases=fetch_run.aliases,
            source_configs=fetch_run.source_configs,
        )
