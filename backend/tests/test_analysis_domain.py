from __future__ import annotations

from datetime import date, datetime, timezone

from app.domain import (
    AnalysisReadyBundle,
    GlobalAnalysisStats,
    NamedCount,
    NormalizedDate,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    SourceName,
    SourceTrace,
    TargetOverviewFacts,
    TargetQuery,
)


def test_analysis_ready_bundle_accepts_typed_section_inputs() -> None:
    query = TargetQuery(target="HER2", aliases=["ERBB2"])
    trial = NormalizedTrialRecord(
        trial_key="NCT00000001",
        nct_id="NCT00000001",
        source_traces=[
            SourceTrace(
                raw_record_id="raw-trial-1",
                fetch_run_id="fetch-1",
                source_name=SourceName.CLINICALTRIALS,
                source_id="NCT00000001",
                source_url="https://clinicaltrials.gov/study/NCT00000001",
                retrieved_at=datetime.now(timezone.utc),
            )
        ],
        phase="PHASE2",
        overall_status="RECRUITING",
        lead_sponsor="Example Sponsor",
    )
    literature = NormalizedLiteratureRecord(
        literature_key="pmid-1",
        pmid="12345678",
        source_traces=[
            SourceTrace(
                raw_record_id="raw-paper-1",
                fetch_run_id="fetch-1",
                source_name=SourceName.PUBMED,
                source_id="12345678",
                source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
                retrieved_at=datetime.now(timezone.utc),
            )
        ],
        title="HER2 study",
        publication_date=NormalizedDate(value=date(2025, 1, 1)),
    )

    bundle = AnalysisReadyBundle(
        query=query,
        trials=[trial],
        literature=[literature],
        global_stats=GlobalAnalysisStats(
            total_trial_count=1,
            total_literature_count=1,
            top_sponsors=[NamedCount(name="Example Sponsor", count=1)],
        ),
    )
    bundle.section_inputs.target_overview.facts = TargetOverviewFacts(
        alias_terms=["HER2", "ERBB2"],
        representative_paper_keys=["pmid-1"],
    )
    bundle.section_inputs.pipeline_overview.trial_keys = ["NCT00000001"]
    bundle.section_inputs.research_update.literature_keys = ["pmid-1"]

    assert bundle.query.target == "HER2"
    assert bundle.section_inputs.target_overview.facts.alias_terms == ["HER2", "ERBB2"]
    assert bundle.section_inputs.pipeline_overview.trial_keys == ["NCT00000001"]
    assert bundle.section_inputs.research_update.literature_keys == ["pmid-1"]


def test_normalized_literature_record_keeps_rich_metadata_slots() -> None:
    record = NormalizedLiteratureRecord(
        literature_key="pmid-2",
        pmid="87654321",
        authors=[],
        affiliations=["Example University"],
        linked_nct_ids=["NCT00000002"],
    )

    assert record.affiliations == ["Example University"]
    assert record.linked_nct_ids == ["NCT00000002"]
