from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_analysis_pipeline_service,
    get_fetch_pipeline_service,
    get_report_generation_service,
)
from app.api.schemas.analysis import AnalysisBundleResponse
from app.api.schemas.fetches import (
    FetchCreateRequest,
    FetchRunResponse,
    RawRecordListResponse,
    RawRecordResponse,
)
from app.api.schemas.reports import (
    ReportResponse,
    ReportSourceRefListResponse,
    ReportSourceRefResponse,
)
from app.domain import SourceName
from app.orchestration import (
    AnalysisPipelineService,
    FetchPipelineService,
    ReportGenerationService,
)

router = APIRouter(prefix="/api/fetches", tags=["fetches"])


@router.post("", response_model=FetchRunResponse)
def create_fetch_run(
    request: FetchCreateRequest,
    service: FetchPipelineService = Depends(get_fetch_pipeline_service),
) -> FetchRunResponse:
    result = service.execute(request.to_target_query())
    return FetchRunResponse(
        fetch_run_id=result.fetch_run_id,
        target=result.target,
        indication=result.indication,
        aliases=result.aliases,
        status=result.status.value,
        raw_record_count=result.raw_record_count,
        source_results=result.source_results,
        warnings=result.warnings,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.get("/{fetch_run_id}", response_model=FetchRunResponse)
def get_fetch_run(
    fetch_run_id: str,
    service: FetchPipelineService = Depends(get_fetch_pipeline_service),
) -> FetchRunResponse:
    result = service.get_fetch_run(fetch_run_id)
    return FetchRunResponse(
        fetch_run_id=result.fetch_run_id,
        target=result.target,
        indication=result.indication,
        aliases=result.aliases,
        status=result.status.value,
        raw_record_count=result.raw_record_count,
        source_results=result.source_results,
        warnings=result.warnings,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.get("/{fetch_run_id}/records", response_model=RawRecordListResponse)
def list_raw_records(
    fetch_run_id: str,
    source_name: SourceName | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: FetchPipelineService = Depends(get_fetch_pipeline_service),
) -> RawRecordListResponse:
    records = service.list_raw_records(
        fetch_run_id,
        source_name=source_name,
        limit=limit,
        offset=offset,
    )
    return RawRecordListResponse(
        fetch_run_id=fetch_run_id,
        total_items=len(records),
        limit=limit,
        offset=offset,
        items=[
            RawRecordResponse(
                record_id=record.record_id,
                fetch_run_id=record.fetch_run_id,
                source_name=record.source_name,
                source_id=record.source_id,
                source_url=record.source_url,
                target=record.target,
                indication=record.indication,
                query_snapshot=record.query_snapshot,
                retrieved_at=record.retrieved_at,
            )
            for record in records
        ],
    )


@router.post("/{fetch_run_id}/analysis", response_model=AnalysisBundleResponse)
def build_analysis_bundle(
    fetch_run_id: str,
    service: AnalysisPipelineService = Depends(get_analysis_pipeline_service),
) -> AnalysisBundleResponse:
    bundle = service.build(fetch_run_id)
    return AnalysisBundleResponse.from_domain(fetch_run_id=fetch_run_id, bundle=bundle)


@router.get("/{fetch_run_id}/analysis", response_model=AnalysisBundleResponse)
def get_analysis_bundle(
    fetch_run_id: str,
    service: AnalysisPipelineService = Depends(get_analysis_pipeline_service),
) -> AnalysisBundleResponse:
    bundle = service.get_bundle(fetch_run_id)
    return AnalysisBundleResponse.from_domain(fetch_run_id=fetch_run_id, bundle=bundle)


@router.post("/{fetch_run_id}/report", response_model=ReportResponse)
def build_report(
    fetch_run_id: str,
    service: ReportGenerationService = Depends(get_report_generation_service),
) -> ReportResponse:
    report = service.build(fetch_run_id)
    return ReportResponse.from_domain(report)


@router.get("/{fetch_run_id}/report", response_model=ReportResponse)
def get_report(
    fetch_run_id: str,
    service: ReportGenerationService = Depends(get_report_generation_service),
) -> ReportResponse:
    report = service.get_report(fetch_run_id)
    return ReportResponse.from_domain(report)


@router.get("/{fetch_run_id}/report/sources", response_model=ReportSourceRefListResponse)
def list_report_sources(
    fetch_run_id: str,
    service: ReportGenerationService = Depends(get_report_generation_service),
) -> ReportSourceRefListResponse:
    report = service.get_report(fetch_run_id)
    items = service.list_sources(fetch_run_id)
    return ReportSourceRefListResponse(
        fetch_run_id=fetch_run_id,
        report_id=report.report_id,
        total_items=len(items),
        items=[ReportSourceRefResponse.from_domain(item) for item in items],
    )
