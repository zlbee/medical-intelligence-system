from __future__ import annotations

from sqlalchemy.orm import Session

from app.analyze import AnalysisBundleBuilder
from app.domain import AnalysisReadyBundle, SourceName, TargetQuery
from app.infra.exceptions import AppException
from app.normalize import LiteratureNormalizer, TrialNormalizer
from app.repository import (
    AnalysisSnapshotRepository,
    FetchRunRepository,
    NormalizedLiteratureRecordRepository,
    NormalizedTrialRecordRepository,
    RawRecordRepository,
)


class AnalysisPipelineService:
    """Runs stage 2 from persisted raw records to a reusable analysis snapshot."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.fetch_run_repository = FetchRunRepository(session)
        self.raw_record_repository = RawRecordRepository(session)
        self.normalized_trial_record_repository = NormalizedTrialRecordRepository(session)
        self.normalized_literature_record_repository = NormalizedLiteratureRecordRepository(
            session
        )
        self.analysis_snapshot_repository = AnalysisSnapshotRepository(session)
        self.trial_normalizer = TrialNormalizer()
        self.literature_normalizer = LiteratureNormalizer()
        self.bundle_builder = AnalysisBundleBuilder()

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

        trials = self.trial_normalizer.normalize_many(raw_records)
        literature = self.literature_normalizer.normalize_many(raw_records)

        self.normalized_trial_record_repository.replace_for_fetch_run(fetch_run_id, trials)
        self.normalized_literature_record_repository.replace_for_fetch_run(
            fetch_run_id,
            literature,
        )

        bundle = self.bundle_builder.build(
            query=self._to_target_query(fetch_run),
            trials=trials,
            literature=literature,
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
