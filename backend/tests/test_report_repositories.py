from __future__ import annotations

from app.domain import AnalysisDimensionName, ReportSourceRef, ReportSourceType
from app.infra.db import SessionLocal, initialize_database
from app.repository import ReportRepository, ReportSourceRefRepository
from tests.report_testkit import (
    build_sample_report,
    clear_all_tables,
    seed_stage_two_artifacts,
)


def test_report_repository_replaces_latest_report_for_fetch_run() -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, _ = seed_stage_two_artifacts(session)
    repository = ReportRepository(session)

    first_report = build_sample_report(fetch_run_id)
    second_report = build_sample_report(fetch_run_id)
    second_report.report_id = "report-2"
    second_report.markdown_content = "# Updated report\n"

    repository.replace_for_fetch_run(first_report)
    repository.replace_for_fetch_run(second_report)
    stored = repository.get_by_fetch_run(fetch_run_id)

    assert stored is not None
    assert stored.report_id == "report-2"
    assert stored.markdown_content == "# Updated report\n"

    session.close()


def test_report_source_ref_repository_replaces_and_sorts_refs() -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, _ = seed_stage_two_artifacts(session)
    repository = ReportSourceRefRepository(session)

    repository.replace_for_fetch_run(
        fetch_run_id=fetch_run_id,
        refs=[
            ReportSourceRef(
                report_id="report-1",
                fetch_run_id=fetch_run_id,
                section_name=AnalysisDimensionName.RESEARCH_UPDATE,
                source_type=ReportSourceType.LITERATURE,
                record_key="paper-1",
                source_id="12345678",
                display_title="Paper 1",
                display_order=2,
            ),
            ReportSourceRef(
                report_id="report-1",
                fetch_run_id=fetch_run_id,
                section_name=AnalysisDimensionName.TARGET_OVERVIEW,
                source_type=ReportSourceType.TRIAL,
                record_key="trial-1",
                source_id="NCT03188393",
                display_title="Trial 1",
                display_order=1,
            ),
            ReportSourceRef(
                report_id="report-1",
                fetch_run_id=fetch_run_id,
                section_name=AnalysisDimensionName.RESEARCH_UPDATE,
                source_type=ReportSourceType.LITERATURE,
                record_key="paper-0",
                source_id="11111111",
                display_title="Paper 0",
                display_order=1,
            ),
        ],
    )
    repository.replace_for_fetch_run(
        fetch_run_id=fetch_run_id,
        refs=[
            ReportSourceRef(
                report_id="report-2",
                fetch_run_id=fetch_run_id,
                section_name=AnalysisDimensionName.PIPELINE_OVERVIEW,
                source_type=ReportSourceType.TRIAL,
                record_key="trial-2",
                source_id="NCT09999999",
                display_title="Trial 2",
                display_order=2,
            ),
            ReportSourceRef(
                report_id="report-2",
                fetch_run_id=fetch_run_id,
                section_name=AnalysisDimensionName.PIPELINE_OVERVIEW,
                source_type=ReportSourceType.TRIAL,
                record_key="trial-1",
                source_id="NCT03188393",
                display_title="Trial 1",
                display_order=1,
            ),
        ],
    )

    refs = repository.list_by_fetch_run(fetch_run_id)

    assert [item.report_id for item in refs] == ["report-2", "report-2"]
    assert [item.record_key for item in refs] == ["trial-1", "trial-2"]

    session.close()
