from __future__ import annotations

from app.domain import AnalysisDimensionName, ReportDocument

SECTION_ORDER = [
    AnalysisDimensionName.TARGET_OVERVIEW,
    AnalysisDimensionName.PIPELINE_OVERVIEW,
    AnalysisDimensionName.RESEARCH_UPDATE,
    AnalysisDimensionName.COMPETITION_ASSESSMENT,
]


class MarkdownRenderer:
    """Renders persisted report sections into the canonical markdown document."""

    def render(self, report: ReportDocument) -> str:
        lines = [
            f"# {report.target} 医疗情报报告",
            "",
            f"- Fetch Run ID: `{report.fetch_run_id}`",
            f"- Analysis Bundle ID: `{report.analysis_bundle_id}`",
            f"- 生成时间: `{report.generated_at.isoformat()}`",
        ]
        if report.indication:
            lines.append(f"- 适应症上下文: `{report.indication}`")
        if report.model:
            lines.append(f"- 模型: `{report.model}`")
        if report.prompt_versions:
            lines.append(f"- Prompt Versions: {', '.join(report.prompt_versions)}")
        lines.append("")

        if report.warning_summary:
            lines.extend(["## 风险提示", ""])
            for item in report.warning_summary:
                lines.append(f"- `{item.code}` {item.message} ({item.count} 次)")
            lines.append("")

        section_map = {section.section_name: section for section in report.sections}
        for section_name in SECTION_ORDER:
            section = section_map.get(section_name)
            if section is None:
                continue
            lines.extend([f"## {section.title}", ""])
            if section.summary:
                lines.extend([section.summary.strip(), ""])
            if section.markdown_body:
                lines.extend([section.markdown_body.strip(), ""])
            if section.key_takeaways:
                lines.extend(["**关键要点**", ""])
                lines.extend([f"- {item}" for item in section.key_takeaways])
                lines.append("")
            if section.warnings:
                lines.extend(["**章节提示**", ""])
                lines.extend([f"- {item}" for item in section.warnings])
                lines.append("")

        return "\n".join(lines).strip() + "\n"
