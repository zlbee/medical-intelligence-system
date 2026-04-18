from __future__ import annotations

from datetime import datetime, timezone

from app.domain import (
    AnalysisDimensionName,
    ReportDocument,
    ReportSection,
    ReportWarningSummary,
)
from app.report import MarkdownRenderer


def test_markdown_renderer_outputs_sections_in_fixed_order() -> None:
    report = ReportDocument(
        fetch_run_id="fetch-run-1",
        analysis_bundle_id="bundle-1",
        target="HER2",
        indication="breast cancer",
        markdown_content="",
        sections=[
            ReportSection(
                section_name=AnalysisDimensionName.COMPETITION_ASSESSMENT,
                title="竞争格局判断",
                summary="竞争摘要",
                markdown_body="竞争正文",
            ),
            ReportSection(
                section_name=AnalysisDimensionName.TARGET_OVERVIEW,
                title="靶点概述",
                summary="靶点摘要",
                markdown_body="靶点正文",
            ),
            ReportSection(
                section_name=AnalysisDimensionName.RESEARCH_UPDATE,
                title="近期研究动态",
                summary="研究摘要",
                markdown_body="研究正文",
            ),
            ReportSection(
                section_name=AnalysisDimensionName.PIPELINE_OVERVIEW,
                title="在研管线概览",
                summary="管线摘要",
                markdown_body="管线正文",
            ),
        ],
        warning_summary=[
            ReportWarningSummary(code="report_context_reference_missing", message="缺少部分来源", count=1)
        ],
        generated_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    markdown = MarkdownRenderer().render(report)

    assert markdown.index("## 靶点概述") < markdown.index("## 在研管线概览")
    assert markdown.index("## 在研管线概览") < markdown.index("## 近期研究动态")
    assert markdown.index("## 近期研究动态") < markdown.index("## 竞争格局判断")
    assert "`report_context_reference_missing` 缺少部分来源 (1 次)" in markdown


def test_markdown_renderer_keeps_section_warning_block() -> None:
    report = ReportDocument(
        fetch_run_id="fetch-run-1",
        analysis_bundle_id="bundle-1",
        target="HER2",
        indication="breast cancer",
        markdown_content="",
        sections=[
            ReportSection(
                section_name=AnalysisDimensionName.TARGET_OVERVIEW,
                title="靶点概述",
                summary="LLM 失败，已降级。",
                markdown_body="以下内容基于阶段 2 的结构化事实自动整理。",
                key_takeaways=["当前章节纳入试验证据 1 条。"],
                warnings=["本章节生成失败，建议人工复核。"],
            )
        ],
    )

    markdown = MarkdownRenderer().render(report)

    assert "**关键要点**" in markdown
    assert "**章节提示**" in markdown
    assert "- 本章节生成失败，建议人工复核。" in markdown
