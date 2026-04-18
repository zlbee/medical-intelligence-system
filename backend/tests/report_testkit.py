from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete

from app.domain import (
    AbstractSection,
    AnalysisReadyBundle,
    CoverageSnapshot,
    DimensionInsight,
    DimensionInsightBreakdown,
    FinalScoreBreakdown,
    GlobalAnalysisStats,
    LLMEnrichmentSummary,
    LLMScoreBreakdown,
    LiteratureLLMEnrichment,
    NamedCount,
    NormalizedDate,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    ReportDocument,
    ReportSection,
    ReportSourceRef,
    ReportSourceType,
    ReportWarningSummary,
    RuleScoreBreakdown,
    SECTION_TITLES,
    SourceName,
    SourceTrace,
    TargetQuery,
    TrialLLMEnrichment,
    WarningItem,
    WarningLevel,
    WarningScope,
)
from app.repository import (
    AnalysisSnapshotRepository,
    FetchRunRepository,
    LiteratureLLMEnrichmentRepository,
    TrialLLMEnrichmentRepository,
)
from app.repository.models import (
    AnalysisSnapshotModel,
    FetchRunModel,
    FetchRunRawRecordModel,
    LiteratureLLMEnrichmentModel,
    NormalizedLiteratureRecordModel,
    NormalizedTrialRecordModel,
    RawRecordModel,
    ReportModel,
    ReportSourceRefModel,
    TrialLLMEnrichmentModel,
)


def build_sample_trial() -> NormalizedTrialRecord:
    return NormalizedTrialRecord(
        trial_key="NCT03188393",
        nct_id="NCT03188393",
        source_traces=[
            SourceTrace(
                raw_record_id="raw-trial-1",
                fetch_run_id="fetch-run-1",
                source_name=SourceName.CLINICALTRIALS,
                source_id="NCT03188393",
                source_url="https://clinicaltrials.gov/study/NCT03188393",
                retrieved_at=datetime.now(timezone.utc),
            )
        ],
        brief_title="HER2 Phase 2 Trial",
        summary="A phase 2 HER2-positive breast cancer study with Example Drug.",
        phase="PHASE2",
        overall_status="RECRUITING",
        lead_sponsor="Example Sponsor",
        conditions=["Breast Cancer"],
        interventions=[],
        countries=["United States"],
        has_results=False,
    )


def build_sample_literature() -> NormalizedLiteratureRecord:
    return NormalizedLiteratureRecord(
        literature_key="12345678",
        pmid="12345678",
        doi="10.1000/example",
        source_traces=[
            SourceTrace(
                raw_record_id="raw-paper-1",
                fetch_run_id="fetch-run-1",
                source_name=SourceName.PUBMED,
                source_id="12345678",
                source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
                retrieved_at=datetime.now(timezone.utc),
            )
        ],
        title="HER2-targeted therapy update",
        journal="Clinical Cancer Research",
        publication_date=NormalizedDate(value=date(2025, 7, 1)),
        publication_types=["Clinical Trial", "Review"],
        abstract_sections=[
            AbstractSection(
                text="HER2-targeted therapy update with efficacy and safety discussion."
            )
        ],
        keywords=["HER2", "breast cancer"],
        mesh_terms=["Breast Neoplasms", "Receptor, ErbB-2"],
        linked_nct_ids=["NCT03188393"],
    )


def build_sample_trial_enrichment(fetch_run_id: str) -> TrialLLMEnrichment:
    return TrialLLMEnrichment(
        fetch_run_id=fetch_run_id,
        trial_key="NCT03188393",
        nct_id="NCT03188393",
        dimension_insights=DimensionInsightBreakdown(
            pipeline_overview=DimensionInsight(
                can_contribute=True,
                relevance_score=92,
                confidence=84,
                summary="Active phase 2 HER2 asset.",
                key_points=["Recruiting phase 2 study.", "Sponsor identifiable."],
            ),
            competition_assessment=DimensionInsight(
                can_contribute=True,
                relevance_score=81,
                confidence=79,
                summary="Useful competition evidence.",
                key_points=["Sponsor and phase support competition analysis."],
            ),
            target_overview=DimensionInsight(
                can_contribute=True,
                relevance_score=60,
                confidence=70,
                summary="Provides disease and intervention context.",
            ),
            research_update=DimensionInsight(
                can_contribute=False,
                relevance_score=20,
                confidence=65,
                summary="Limited recent-readout value.",
            ),
        ),
        rule_scores=RuleScoreBreakdown(
            target_overview=55,
            pipeline_overview=76,
            research_update=25,
            competition_assessment=80,
            overall_score=66,
        ),
        llm_scores=LLMScoreBreakdown(
            target_overview=62,
            pipeline_overview=90,
            research_update=35,
            competition_assessment=84,
            overall_score=74,
        ),
        final_scores=FinalScoreBreakdown(
            target_overview=57.45,
            pipeline_overview=80.9,
            research_update=28.5,
            competition_assessment=81.4,
            overall_score=69.15,
        ),
        modality="drug",
        asset_candidates=["Example Drug"],
        company_candidates=["Example Sponsor"],
        risk_signals=["No published results yet."],
        opportunity_signals=["Recruiting phase 2 study."],
        model="test-model",
        prompt_version="trial_enrichment_v1",
    )


def build_sample_literature_enrichment(fetch_run_id: str) -> LiteratureLLMEnrichment:
    return LiteratureLLMEnrichment(
        fetch_run_id=fetch_run_id,
        literature_key="12345678",
        pmid="12345678",
        doi="10.1000/example",
        dimension_insights=DimensionInsightBreakdown(
            target_overview=DimensionInsight(
                can_contribute=True,
                relevance_score=88,
                confidence=86,
                summary="Strong target and mechanism context.",
                key_points=["Summarizes HER2-targeted therapy themes."],
            ),
            research_update=DimensionInsight(
                can_contribute=True,
                relevance_score=94,
                confidence=89,
                summary="Recent and high-value literature.",
                key_points=["Recent publication in a named journal."],
            ),
            competition_assessment=DimensionInsight(
                can_contribute=True,
                relevance_score=72,
                confidence=75,
                summary="Mentions NCT-linked evidence.",
                key_points=["Contains NCT linkage."],
            ),
            pipeline_overview=DimensionInsight(
                can_contribute=False,
                relevance_score=30,
                confidence=61,
                summary="Pipeline utility is secondary.",
            ),
        ),
        rule_scores=RuleScoreBreakdown(
            target_overview=82,
            pipeline_overview=45,
            research_update=91,
            competition_assessment=67,
            overall_score=75.2,
        ),
        llm_scores=LLMScoreBreakdown(
            target_overview=90,
            pipeline_overview=35,
            research_update=95,
            competition_assessment=75,
            overall_score=81,
        ),
        final_scores=FinalScoreBreakdown(
            target_overview=84.8,
            pipeline_overview=41.5,
            research_update=92.4,
            competition_assessment=69.8,
            overall_score=79.43,
        ),
        study_design="Review",
        mechanism_themes=["HER2 signaling", "targeted therapy"],
        efficacy_signals=["Response improvement reported."],
        safety_signals=["Manageable safety profile discussed."],
        trial_link_hints=["NCT03188393"],
        model="test-model",
        prompt_version="literature_enrichment_v1",
    )


def build_sample_analysis_bundle(fetch_run_id: str) -> AnalysisReadyBundle:
    trial = build_sample_trial()
    literature = build_sample_literature()
    bundle = AnalysisReadyBundle(
        bundle_id="bundle-1",
        query=TargetQuery(target="HER2", indication="breast cancer", aliases=["ERBB2"]),
        trials=[trial],
        literature=[literature],
        trial_llm_enrichments=[build_sample_trial_enrichment(fetch_run_id)],
        literature_llm_enrichments=[build_sample_literature_enrichment(fetch_run_id)],
        global_stats=GlobalAnalysisStats(
            total_trial_count=1,
            total_literature_count=1,
            trial_phase_distribution={"PHASE2": 1},
            top_sponsors=[NamedCount(name="Example Sponsor", count=1)],
            top_journals=[NamedCount(name="Clinical Cancer Research", count=1)],
            top_mesh_terms=[NamedCount(name="Breast Neoplasms", count=1)],
            top_keywords=[NamedCount(name="HER2", count=1)],
            publication_count_by_year={2025: 1},
            literature_with_nct_mentions_count=1,
        ),
        coverage=CoverageSnapshot(
            has_trial_evidence=True,
            has_literature_evidence=True,
            has_target_overview_evidence=True,
            has_pipeline_overview_evidence=True,
            has_research_update_evidence=True,
            has_competition_assessment_evidence=True,
        ),
        llm_enrichment_summary=LLMEnrichmentSummary(
            trial_total=1,
            trial_succeeded=1,
            literature_total=1,
            literature_succeeded=1,
            warning_count=0,
            model="test-model",
            prompt_versions=["trial_enrichment_v1", "literature_enrichment_v1"],
        ),
    )
    bundle.section_inputs.target_overview.trial_keys = ["NCT03188393"]
    bundle.section_inputs.target_overview.literature_keys = ["12345678"]
    bundle.section_inputs.target_overview.facts.alias_terms = ["HER2", "ERBB2"]
    bundle.section_inputs.target_overview.facts.disease_contexts = ["breast cancer"]
    bundle.section_inputs.target_overview.facts.representative_paper_keys = ["12345678"]
    bundle.section_inputs.pipeline_overview.trial_keys = ["NCT03188393"]
    bundle.section_inputs.pipeline_overview.facts.phase_distribution = {"PHASE2": 1}
    bundle.section_inputs.pipeline_overview.facts.active_trial_count = 1
    bundle.section_inputs.pipeline_overview.facts.top_sponsors = [
        NamedCount(name="Example Sponsor", count=1)
    ]
    bundle.section_inputs.research_update.literature_keys = ["12345678"]
    bundle.section_inputs.research_update.facts.publication_count_by_year = {2025: 1}
    bundle.section_inputs.research_update.facts.recent_paper_keys = ["12345678"]
    bundle.section_inputs.research_update.facts.high_value_paper_keys = ["12345678"]
    bundle.section_inputs.competition_assessment.trial_keys = ["NCT03188393"]
    bundle.section_inputs.competition_assessment.literature_keys = ["12345678"]
    bundle.section_inputs.competition_assessment.facts.active_sponsor_count = 1
    bundle.section_inputs.competition_assessment.facts.late_stage_trial_count = 0
    bundle.section_inputs.competition_assessment.facts.recruiting_trial_count = 1
    bundle.section_inputs.competition_assessment.facts.literature_with_nct_mentions_count = 1
    return bundle


def seed_stage_two_artifacts(session) -> tuple[str, AnalysisReadyBundle]:
    fetch_run = FetchRunRepository(session).create(
        TargetQuery(target="HER2", indication="breast cancer", aliases=["ERBB2"])
    )
    fetch_run_id = fetch_run.fetch_run_id
    bundle = build_sample_analysis_bundle(fetch_run_id)
    for trace in bundle.trials[0].source_traces:
        trace.fetch_run_id = fetch_run_id
    for trace in bundle.literature[0].source_traces:
        trace.fetch_run_id = fetch_run_id
    bundle.trial_llm_enrichments = [build_sample_trial_enrichment(fetch_run_id)]
    bundle.literature_llm_enrichments = [build_sample_literature_enrichment(fetch_run_id)]

    AnalysisSnapshotRepository(session).upsert(fetch_run_id, bundle)
    TrialLLMEnrichmentRepository(session).replace_for_fetch_run(
        fetch_run_id,
        bundle.trial_llm_enrichments,
    )
    LiteratureLLMEnrichmentRepository(session).replace_for_fetch_run(
        fetch_run_id,
        bundle.literature_llm_enrichments,
    )
    return fetch_run_id, bundle


def build_sample_report(fetch_run_id: str) -> ReportDocument:
    section = ReportSection(
        section_name=list(SECTION_TITLES.keys())[0],
        title="靶点概述",
        summary="HER2 是当前章节的核心靶点。",
        markdown_body="本节聚焦 HER2 的疾病语境与研究主题。",
        key_takeaways=["证据主要来自近期文献。"],
        trial_keys=["NCT03188393"],
        literature_keys=["12345678"],
    )
    warning = WarningItem(
        code="report_context_reference_missing",
        level=WarningLevel.WARNING,
        scope=WarningScope.SECTION,
        message="Example warning.",
        related_ids=[fetch_run_id],
    )
    source_ref = ReportSourceRef(
        report_id="report-1",
        fetch_run_id=fetch_run_id,
        section_name=section.section_name,
        source_type=ReportSourceType.LITERATURE,
        record_key="12345678",
        source_id="12345678",
        display_title="HER2-targeted therapy update",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        display_order=1,
    )
    return ReportDocument(
        report_id="report-1",
        fetch_run_id=fetch_run_id,
        analysis_bundle_id="bundle-1",
        target="HER2",
        indication="breast cancer",
        markdown_content="# HER2 医疗情报报告\n",
        sections=[section],
        warnings=[warning],
        warning_summary=[
            ReportWarningSummary(code=warning.code, message=warning.message, count=1)
        ],
        source_refs=[source_ref],
        model="test-model",
        prompt_versions=["target_overview_report_v1"],
    )


def clear_all_tables(session) -> None:
    session.execute(delete(ReportSourceRefModel))
    session.execute(delete(ReportModel))
    session.execute(delete(AnalysisSnapshotModel))
    session.execute(delete(LiteratureLLMEnrichmentModel))
    session.execute(delete(TrialLLMEnrichmentModel))
    session.execute(delete(NormalizedLiteratureRecordModel))
    session.execute(delete(NormalizedTrialRecordModel))
    session.execute(delete(FetchRunRawRecordModel))
    session.execute(delete(RawRecordModel))
    session.execute(delete(FetchRunModel))
    session.commit()
