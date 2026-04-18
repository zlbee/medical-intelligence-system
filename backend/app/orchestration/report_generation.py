from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.domain import (
    AnalysisDimensionName,
    GeneratedSectionDraft,
    ReportDocument,
    ReportSection,
    ReportSourceRef,
    ReportSourceType,
    ReportWarningSummary,
    SECTION_TITLES,
    SectionGenerationContext,
    WarningItem,
    WarningLevel,
    WarningScope,
)
from app.infra.exceptions import AppException
from app.llm import LLMClient
from app.report import (
    CompetitionAssessmentReportGenerator,
    MarkdownRenderer,
    PipelineOverviewReportGenerator,
    ReportContextBuilder,
    ResearchUpdateReportGenerator,
    TargetOverviewReportGenerator,
)
from app.repository import (
    AnalysisSnapshotRepository,
    FetchRunRepository,
    LiteratureLLMEnrichmentRepository,
    ReportRepository,
    ReportSourceRefRepository,
    TrialLLMEnrichmentRepository,
)

SECTION_ORDER = [
    AnalysisDimensionName.TARGET_OVERVIEW,
    AnalysisDimensionName.PIPELINE_OVERVIEW,
    AnalysisDimensionName.RESEARCH_UPDATE,
    AnalysisDimensionName.COMPETITION_ASSESSMENT,
]


class ReportGenerationService:
    """Builds one latest persisted report per fetch run from stage-2 database artifacts."""

    def __init__(
        self,
        session: Session,
        *,
        llm_client: LLMClient | None = None,
        llm_model: str | None = None,
        report_output_dir: str | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.report_output_dir = report_output_dir
        self.fetch_run_repository = FetchRunRepository(session)
        self.analysis_snapshot_repository = AnalysisSnapshotRepository(session)
        self.trial_llm_enrichment_repository = TrialLLMEnrichmentRepository(session)
        self.literature_llm_enrichment_repository = LiteratureLLMEnrichmentRepository(session)
        self.report_repository = ReportRepository(session)
        self.report_source_ref_repository = ReportSourceRefRepository(session)
        self.context_builder = ReportContextBuilder(
            analysis_snapshot_repository=self.analysis_snapshot_repository,
            trial_llm_enrichment_repository=self.trial_llm_enrichment_repository,
            literature_llm_enrichment_repository=self.literature_llm_enrichment_repository,
        )
        self.renderer = MarkdownRenderer()
        self.generators = (
            {
                AnalysisDimensionName.TARGET_OVERVIEW: TargetOverviewReportGenerator(
                    llm_client,
                    model=llm_model,
                ),
                AnalysisDimensionName.PIPELINE_OVERVIEW: PipelineOverviewReportGenerator(
                    llm_client,
                    model=llm_model,
                ),
                AnalysisDimensionName.RESEARCH_UPDATE: ResearchUpdateReportGenerator(
                    llm_client,
                    model=llm_model,
                ),
                AnalysisDimensionName.COMPETITION_ASSESSMENT: CompetitionAssessmentReportGenerator(
                    llm_client,
                    model=llm_model,
                ),
            }
            if llm_client is not None
            else {}
        )

    def build(self, fetch_run_id: str) -> ReportDocument:
        fetch_run = self.fetch_run_repository.get(fetch_run_id)
        if fetch_run is None:
            raise AppException(
                "Fetch run not found.",
                code="fetch_run_not_found",
                status_code=404,
                details={"fetch_run_id": fetch_run_id},
            )
        if self.llm_client is None or not self.generators:
            raise AppException(
                "LLM client is required for report generation.",
                code="report_llm_unavailable",
                status_code=503,
                details={"fetch_run_id": fetch_run_id, "model": self.llm_model},
            )

        bundle, contexts, warnings = self.context_builder.build(fetch_run_id)
        warnings = [*bundle.warnings, *warnings]
        sections: list[ReportSection] = []
        failed_sections: list[str] = []
        prompt_versions: list[str] = []

        for section_name in SECTION_ORDER:
            context = contexts[section_name]
            generator = self.generators[section_name]
            prompt_versions.append(generator.prompt_version)
            try:
                draft = generator.generate(context)
                section, section_warnings = self._build_report_section(context, draft)
                warnings.extend(section_warnings)
            except Exception as exc:  # noqa: BLE001 - section-level best effort is intentional.
                failed_sections.append(section_name.value)
                failure_message = (
                    f"{context.title} 章节生成失败，已回退为基于结构化事实的最小摘要。"
                )
                warnings.append(
                    WarningItem(
                        code="report_section_generation_failed",
                        level=WarningLevel.WARNING,
                        scope=WarningScope.SECTION,
                        message=failure_message,
                        related_ids=[fetch_run_id, section_name.value],
                        details={
                            "section_name": section_name.value,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                )
                section = self._build_fallback_section(context, failure_message)
            sections.append(section)

        if len(failed_sections) == len(SECTION_ORDER):
            raise AppException(
                "All report sections failed to generate.",
                code="report_generation_failed",
                status_code=502,
                details={"fetch_run_id": fetch_run_id, "failed_sections": failed_sections},
            )

        report = ReportDocument(
            fetch_run_id=fetch_run_id,
            analysis_bundle_id=bundle.bundle_id,
            target=bundle.query.target,
            indication=bundle.query.indication,
            markdown_content="",
            sections=sections,
            warnings=warnings,
            warning_summary=self._build_warning_summary(warnings),
            source_refs=[],
            model=self.llm_model,
            prompt_versions=list(dict.fromkeys(prompt_versions)),
        )
        report.source_refs = self._build_source_refs(report, contexts)
        report.markdown_content = self.renderer.render(report)

        mirror_warning = self._write_markdown_copy(report)
        if mirror_warning is not None:
            report.warnings.append(mirror_warning)
            report.warning_summary = self._build_warning_summary(report.warnings)
            report.markdown_content = self.renderer.render(report)

        self.report_repository.replace_for_fetch_run(report)
        self.report_source_ref_repository.replace_for_fetch_run(
            fetch_run_id=fetch_run_id,
            refs=report.source_refs,
        )
        return self.get_report(fetch_run_id)

    def get_report(self, fetch_run_id: str) -> ReportDocument:
        report = self.report_repository.get_by_fetch_run(fetch_run_id)
        if report is None:
            raise AppException(
                "Report not found for the fetch run.",
                code="report_not_found",
                status_code=404,
                details={"fetch_run_id": fetch_run_id},
            )
        return report

    def list_sources(self, fetch_run_id: str) -> list[ReportSourceRef]:
        self.get_report(fetch_run_id)
        return self.report_source_ref_repository.list_by_fetch_run(fetch_run_id)

    def _build_report_section(
        self,
        context: SectionGenerationContext,
        draft: GeneratedSectionDraft,
    ) -> tuple[ReportSection, list[WarningItem]]:
        warnings: list[WarningItem] = []
        allowed_trial_keys = {record.trial_key for record in context.trials}
        allowed_literature_keys = {record.literature_key for record in context.literature}

        filtered_trial_keys = [key for key in draft.trial_keys if key in allowed_trial_keys]
        filtered_literature_keys = [
            key for key in draft.literature_keys if key in allowed_literature_keys
        ]
        rejected_trial_keys = [key for key in draft.trial_keys if key not in allowed_trial_keys]
        rejected_literature_keys = [
            key for key in draft.literature_keys if key not in allowed_literature_keys
        ]

        if rejected_trial_keys or rejected_literature_keys:
            warnings.append(
                WarningItem(
                    code="report_section_reference_filtered",
                    level=WarningLevel.WARNING,
                    scope=WarningScope.SECTION,
                    message=(
                        f"{context.title} 章节引用了超出当前上下文的记录 key，相关引用已被忽略。"
                    ),
                    related_ids=[context.fetch_run_id, context.section_name.value],
                    details={
                        "section_name": context.section_name.value,
                        "rejected_trial_keys": rejected_trial_keys,
                        "rejected_literature_keys": rejected_literature_keys,
                    },
                )
            )

        section_warnings = [*context.warnings, *draft.warnings]
        if rejected_trial_keys or rejected_literature_keys:
            section_warnings.append("已过滤超出当前章节上下文范围的引用 key。")

        return (
            ReportSection(
                section_name=context.section_name,
                title=context.title,
                summary=draft.summary.strip(),
                markdown_body=draft.markdown_body.strip(),
                key_takeaways=draft.key_takeaways,
                trial_keys=filtered_trial_keys,
                literature_keys=filtered_literature_keys,
                warnings=section_warnings,
            ),
            warnings,
        )

    def _build_fallback_section(
        self,
        context: SectionGenerationContext,
        failure_message: str,
    ) -> ReportSection:
        summary = "本章节的 LLM 生成失败，以下内容基于阶段 2 的结构化事实自动整理。"
        return ReportSection(
            section_name=context.section_name,
            title=context.title,
            summary=summary,
            markdown_body=self._build_fallback_markdown_body(context),
            key_takeaways=self._build_fallback_takeaways(context),
            trial_keys=[record.trial_key for record in context.trials],
            literature_keys=[record.literature_key for record in context.literature],
            warnings=[*context.warnings, failure_message],
        )

    def _build_fallback_markdown_body(self, context: SectionGenerationContext) -> str:
        facts = context.facts
        lines = [
            "以下结论来自阶段 2 的程序统计和已选中的结构化证据，而不是章节级 LLM 文本生成结果。",
            "",
        ]
        if context.section_name == AnalysisDimensionName.TARGET_OVERVIEW:
            lines.extend(
                [
                    f"- 别名: {', '.join(facts.get('alias_terms', [])) or '暂无'}",
                    f"- 疾病语境: {', '.join(facts.get('disease_contexts', [])) or '暂无'}",
                    f"- 代表性文献数: {len(facts.get('representative_paper_keys', []))}",
                    f"- 当前纳入文献/试验: {len(context.literature)} / {len(context.trials)}",
                ]
            )
        elif context.section_name == AnalysisDimensionName.PIPELINE_OVERVIEW:
            lines.extend(
                [
                    f"- 活跃试验数: {facts.get('active_trial_count', 0)}",
                    f"- 已披露结果试验数: {facts.get('results_posted_count', 0)}",
                    f"- 阶段分布: {_format_mapping(facts.get('phase_distribution', {}))}",
                    f"- 主要 sponsor: {_format_named_counts(facts.get('top_sponsors', []))}",
                ]
            )
        elif context.section_name == AnalysisDimensionName.RESEARCH_UPDATE:
            lines.extend(
                [
                    f"- 年度文献数: {_format_mapping(facts.get('publication_count_by_year', {}))}",
                    f"- 近期文献数: {len(facts.get('recent_paper_keys', []))}",
                    f"- 高价值文献数: {len(facts.get('high_value_paper_keys', []))}",
                    f"- 高频期刊: {_format_named_counts(facts.get('top_journals', []))}",
                ]
            )
        else:
            lines.extend(
                [
                    f"- 活跃 sponsor 数: {facts.get('active_sponsor_count', 0)}",
                    f"- 后期项目数: {facts.get('late_stage_trial_count', 0)}",
                    f"- 招募中项目数: {facts.get('recruiting_trial_count', 0)}",
                    f"- 带试验线索文献数: {facts.get('literature_with_nct_mentions_count', 0)}",
                ]
            )
        if context.coverage_notes:
            lines.extend(["", "**Coverage 提示**"])
            lines.extend([f"- {item}" for item in context.coverage_notes])
        return "\n".join(lines)

    def _build_fallback_takeaways(self, context: SectionGenerationContext) -> list[str]:
        return [
            f"当前章节纳入试验证据 {len(context.trials)} 条。",
            f"当前章节纳入文献证据 {len(context.literature)} 条。",
            "由于章节级 LLM 失败，本节应结合来源清单进一步人工复核。",
        ]

    def _build_source_refs(
        self,
        report: ReportDocument,
        contexts: dict[AnalysisDimensionName, SectionGenerationContext],
    ) -> list[ReportSourceRef]:
        refs: list[ReportSourceRef] = []
        for section in report.sections:
            display_order = 1
            context = contexts[section.section_name]
            trial_map = {record.trial_key: record for record in context.trials}
            literature_map = {
                record.literature_key: record
                for record in context.literature
            }
            for key in section.trial_keys:
                trial = trial_map.get(key)
                if trial is None:
                    continue
                refs.append(
                    ReportSourceRef(
                        report_id=report.report_id,
                        fetch_run_id=report.fetch_run_id,
                        section_name=section.section_name,
                        source_type=ReportSourceType.TRIAL,
                        record_key=trial.trial_key,
                        source_id=trial.nct_id or trial.trial_key,
                        display_title=trial.brief_title
                        or trial.official_title
                        or trial.nct_id
                        or trial.trial_key,
                        source_url=_first_source_url(trial.source_traces),
                        display_order=display_order,
                        payload={
                            "trial_key": trial.trial_key,
                            "nct_id": trial.nct_id,
                            "phase": trial.phase,
                            "overall_status": trial.overall_status,
                        },
                    )
                )
                display_order += 1
            for key in section.literature_keys:
                paper = literature_map.get(key)
                if paper is None:
                    continue
                refs.append(
                    ReportSourceRef(
                        report_id=report.report_id,
                        fetch_run_id=report.fetch_run_id,
                        section_name=section.section_name,
                        source_type=ReportSourceType.LITERATURE,
                        record_key=paper.literature_key,
                        source_id=paper.pmid or paper.doi or paper.literature_key,
                        display_title=paper.title or paper.pmid or paper.literature_key,
                        source_url=_first_source_url(paper.source_traces),
                        display_order=display_order,
                        payload={
                            "literature_key": paper.literature_key,
                            "pmid": paper.pmid,
                            "doi": paper.doi,
                            "journal": paper.journal,
                        },
                    )
                )
                display_order += 1
        return refs

    def _write_markdown_copy(self, report: ReportDocument) -> WarningItem | None:
        if not self.report_output_dir:
            return None
        try:
            output_dir = Path(self.report_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{report.fetch_run_id}.md"
            output_path.write_text(report.markdown_content, encoding="utf-8")
            return None
        except OSError as exc:
            return WarningItem(
                code="report_markdown_mirror_failed",
                level=WarningLevel.WARNING,
                scope=WarningScope.BUNDLE,
                message="Failed to mirror the latest markdown report to the local reports directory.",
                related_ids=[report.fetch_run_id, report.report_id],
                details={"error_type": type(exc).__name__, "error": str(exc)},
            )

    def _build_warning_summary(
        self,
        warnings: list[WarningItem],
    ) -> list[ReportWarningSummary]:
        grouped: dict[tuple[str, str], int] = {}
        for warning in warnings:
            key = (warning.code, warning.message)
            grouped[key] = grouped.get(key, 0) + 1
        return [
            ReportWarningSummary(code=code, message=message, count=count)
            for (code, message), count in grouped.items()
        ]


def _first_source_url(source_traces) -> str | None:
    for trace in source_traces:
        if trace.source_url:
            return trace.source_url
    return None


def _format_mapping(values: dict[str, object]) -> str:
    if not values:
        return "暂无"
    return " / ".join(f"{key}: {value}" for key, value in values.items())


def _format_named_counts(values: list[dict[str, object]]) -> str:
    if not values:
        return "暂无"
    return " / ".join(f"{item['name']} ({item['count']})" for item in values[:5])
