from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.analysis import WarningItemResponse
from app.domain import ReportDocument, ReportSourceRef


class ReportWarningSummaryResponse(BaseModel):
    code: str
    message: str
    count: int


class ReportSectionResponse(BaseModel):
    section_name: str
    title: str
    summary: str
    markdown_body: str
    key_takeaways: list[str] = Field(default_factory=list)
    trial_keys: list[str] = Field(default_factory=list)
    literature_keys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    report_id: str
    fetch_run_id: str
    analysis_bundle_id: str
    target: str
    indication: str | None = None
    markdown_content: str
    sections: list[ReportSectionResponse] = Field(default_factory=list)
    warnings: list[WarningItemResponse] = Field(default_factory=list)
    warning_summary: list[ReportWarningSummaryResponse] = Field(default_factory=list)
    model: str | None = None
    prompt_versions: list[str] = Field(default_factory=list)
    generated_at: datetime

    @classmethod
    def from_domain(cls, report: ReportDocument) -> "ReportResponse":
        return cls(
            report_id=report.report_id,
            fetch_run_id=report.fetch_run_id,
            analysis_bundle_id=report.analysis_bundle_id,
            target=report.target,
            indication=report.indication,
            markdown_content=report.markdown_content,
            sections=[
                ReportSectionResponse.model_validate(section.model_dump(mode="json"))
                for section in report.sections
            ],
            warnings=[WarningItemResponse.from_domain(item) for item in report.warnings],
            warning_summary=[
                ReportWarningSummaryResponse.model_validate(item.model_dump(mode="json"))
                for item in report.warning_summary
            ],
            model=report.model,
            prompt_versions=report.prompt_versions,
            generated_at=report.generated_at,
        )


class ReportSourceRefResponse(BaseModel):
    report_id: str
    fetch_run_id: str
    section_name: str
    source_type: str
    record_key: str
    source_id: str
    display_title: str
    source_url: str | None = None
    display_order: int

    @classmethod
    def from_domain(cls, ref: ReportSourceRef) -> "ReportSourceRefResponse":
        return cls(
            report_id=ref.report_id,
            fetch_run_id=ref.fetch_run_id,
            section_name=ref.section_name.value,
            source_type=ref.source_type.value,
            record_key=ref.record_key,
            source_id=ref.source_id,
            display_title=ref.display_title,
            source_url=ref.source_url,
            display_order=ref.display_order,
        )


class ReportSourceRefListResponse(BaseModel):
    fetch_run_id: str
    report_id: str
    total_items: int
    items: list[ReportSourceRefResponse] = Field(default_factory=list)
