from __future__ import annotations

from pathlib import Path

from app.domain import AnalysisDimensionName
from app.infra.db import SessionLocal, initialize_database
from app.infra.exceptions import AppException
from app.orchestration import AnalysisPipelineService, ReportGenerationService
from app.repository.models import AnalysisSnapshotModel
from tests.report_testkit import clear_all_tables, seed_stage_two_artifacts


def test_report_generation_service_builds_and_persists_report(tmp_path: Path) -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, bundle = seed_stage_two_artifacts(session)
    service = ReportGenerationService(
        session,
        llm_client=StubLLMClient(
            [
                _section_response(
                    "靶点概述",
                    "靶点摘要",
                    "靶点正文",
                    trial_keys=["NCT03188393", "UNKNOWN"],
                    literature_keys=["12345678"],
                ),
                _section_response(
                    "在研管线概览",
                    "管线摘要",
                    "管线正文",
                    trial_keys=["NCT03188393"],
                ),
                _section_response(
                    "近期研究动态",
                    "研究摘要",
                    "研究正文",
                    literature_keys=["12345678"],
                ),
                _section_response(
                    "竞争格局判断",
                    "竞争摘要",
                    "竞争正文",
                    trial_keys=["NCT03188393"],
                    literature_keys=["12345678"],
                ),
            ]
        ),
        llm_model="test-model",
        report_output_dir=str(tmp_path),
    )

    report = service.build(fetch_run_id)
    persisted = service.get_report(fetch_run_id)
    sources = service.list_sources(fetch_run_id)

    assert report.report_id == persisted.report_id
    assert report.analysis_bundle_id == bundle.bundle_id
    assert len(report.sections) == 4
    assert report.sections[0].section_name == AnalysisDimensionName.TARGET_OVERVIEW
    assert report.sections[0].trial_keys == ["NCT03188393"]
    assert any(item.code == "report_section_reference_filtered" for item in report.warnings)
    assert len(sources) == 6
    assert sources[0].section_name == AnalysisDimensionName.TARGET_OVERVIEW
    assert (tmp_path / f"{fetch_run_id}.md").exists()

    session.close()


def test_report_generation_service_returns_best_effort_when_one_section_fails(
    tmp_path: Path,
) -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, _ = seed_stage_two_artifacts(session)
    service = ReportGenerationService(
        session,
        llm_client=StubLLMClient(
            [
                _section_response(
                    "靶点概述",
                    "靶点摘要",
                    "靶点正文",
                    trial_keys=["NCT03188393"],
                    literature_keys=["12345678"],
                ),
                RuntimeError("synthetic section failure"),
                _section_response(
                    "近期研究动态",
                    "研究摘要",
                    "研究正文",
                    literature_keys=["12345678"],
                ),
                _section_response(
                    "竞争格局判断",
                    "竞争摘要",
                    "竞争正文",
                    trial_keys=["NCT03188393"],
                ),
            ]
        ),
        llm_model="test-model",
        report_output_dir=str(tmp_path),
    )

    report = service.build(fetch_run_id)
    pipeline_section = next(
        item
        for item in report.sections
        if item.section_name == AnalysisDimensionName.PIPELINE_OVERVIEW
    )

    assert "以下结论来自阶段 2 的程序统计和已选中的结构化证据" in pipeline_section.markdown_body
    assert any(item.code == "report_section_generation_failed" for item in report.warnings)

    session.close()


def test_report_generation_service_fails_when_all_sections_fail(tmp_path: Path) -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, _ = seed_stage_two_artifacts(session)
    service = ReportGenerationService(
        session,
        llm_client=StubLLMClient(
            [
                RuntimeError("failure-1"),
                RuntimeError("failure-2"),
                RuntimeError("failure-3"),
                RuntimeError("failure-4"),
            ]
        ),
        llm_model="test-model",
        report_output_dir=str(tmp_path),
    )

    try:
        service.build(fetch_run_id)
        raise AssertionError("Expected all-section failure.")
    except AppException as exc:
        assert exc.status_code == 502
        assert exc.code == "report_generation_failed"
    finally:
        session.close()


def test_report_generation_service_requires_analysis_snapshot(tmp_path: Path) -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id, _ = seed_stage_two_artifacts(session)
    session.execute(AnalysisSnapshotModel.__table__.delete())
    session.commit()
    service = ReportGenerationService(
        session,
        llm_client=StubLLMClient([_section_response("靶点概述", "摘要", "正文")]),
        llm_model="test-model",
        report_output_dir=str(tmp_path),
    )

    try:
        service.build(fetch_run_id)
        raise AssertionError("Expected analysis snapshot requirement error.")
    except AppException as exc:
        assert exc.status_code == 409
        assert exc.code == "analysis_snapshot_required"
    finally:
        session.close()


def test_report_generation_smoke_fetch_analysis_report_sources(tmp_path: Path) -> None:
    initialize_database()
    session = SessionLocal()
    clear_all_tables(session)
    fetch_run_id = _seed_fetch_run(session)
    analysis_bundle = AnalysisPipelineService(session).build(fetch_run_id)
    report = ReportGenerationService(
        session,
        llm_client=StubLLMClient(
            [
                _section_response(
                    "靶点概述",
                    "靶点摘要",
                    "靶点正文",
                    trial_keys=["NCT03188393"],
                    literature_keys=["12345678"],
                ),
                _section_response(
                    "在研管线概览",
                    "管线摘要",
                    "管线正文",
                    trial_keys=["NCT03188393"],
                ),
                _section_response(
                    "近期研究动态",
                    "研究摘要",
                    "研究正文",
                    literature_keys=["12345678"],
                ),
                _section_response(
                    "竞争格局判断",
                    "竞争摘要",
                    "竞争正文",
                    trial_keys=["NCT03188393"],
                    literature_keys=["12345678"],
                ),
            ]
        ),
        llm_model="test-model",
        report_output_dir=str(tmp_path),
    ).build(fetch_run_id)

    assert analysis_bundle.bundle_id == report.analysis_bundle_id
    assert report.source_refs
    assert report.markdown_content.startswith("# HER2 医疗情报报告")

    session.close()


class StubLLMClient:
    def __init__(self, responses: list[dict | Exception]) -> None:
        self.responses = responses

    def generate_structured(self, **kwargs):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return kwargs["response_model"].model_validate(response)


def _section_response(
    title: str,
    summary: str,
    markdown_body: str,
    *,
    trial_keys: list[str] | None = None,
    literature_keys: list[str] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "summary": summary,
        "markdown_body": markdown_body,
        "key_takeaways": ["要点一"],
        "trial_keys": trial_keys or [],
        "literature_keys": literature_keys or [],
        "warnings": [],
    }


def _seed_fetch_run(session) -> str:
    from tests.test_analysis_pipeline import _seed_fetch_run as seed_analysis_fetch_run

    return seed_analysis_fetch_run(session)
