from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.domain import RawRecord, SourceName, TargetQuery
from app.infra.db import SessionLocal, initialize_database
from app.orchestration import AnalysisPipelineService
from app.repository import FetchRunRepository, RawRecordRepository
from app.repository.models import (
    AnalysisSnapshotModel,
    FetchRunModel,
    FetchRunRawRecordModel,
    LiteratureLLMEnrichmentModel,
    NormalizedLiteratureRecordModel,
    NormalizedTrialRecordModel,
    RawRecordModel,
    TrialLLMEnrichmentModel,
)


PUBMED_XML = """
<PubmedArticle>
  <MedlineCitation>
    <PMID Version="1">12345678</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>2025</Year>
            <Month>Jul</Month>
            <Day>01</Day>
          </PubDate>
        </JournalIssue>
        <Title>Clinical Cancer Research</Title>
      </Journal>
      <ArticleTitle>HER2-targeted therapy update.</ArticleTitle>
      <ELocationID EIdType="doi" ValidYN="Y">10.1000/example</ELocationID>
      <Abstract>
        <AbstractText>HER2 therapy background mentioning NCT03188393.</AbstractText>
      </Abstract>
      <AuthorList>
        <Author ValidYN="Y">
          <LastName>Li</LastName>
          <ForeName>Huan</ForeName>
        </Author>
      </AuthorList>
      <DataBankList CompleteYN="Y">
        <DataBank>
          <DataBankName>ClinicalTrials.gov</DataBankName>
          <AccessionNumberList>
            <AccessionNumber>NCT03188393</AccessionNumber>
          </AccessionNumberList>
        </DataBank>
      </DataBankList>
      <PublicationTypeList>
        <PublicationType>Clinical Trial</PublicationType>
      </PublicationTypeList>
    </Article>
    <MeshHeadingList>
      <MeshHeading>
        <DescriptorName>Breast Neoplasms</DescriptorName>
      </MeshHeading>
    </MeshHeadingList>
  </MedlineCitation>
</PubmedArticle>
""".strip()


def test_analysis_pipeline_builds_and_persists_bundle_with_rule_only_fallback() -> None:
    initialize_database()
    session = SessionLocal()
    _clear_tables(session)
    fetch_run_id = _seed_fetch_run(session)

    bundle = AnalysisPipelineService(session).build(fetch_run_id)

    normalized_trial_count = session.scalar(
        select(func.count()).select_from(NormalizedTrialRecordModel)
    )
    normalized_literature_count = session.scalar(
        select(func.count()).select_from(NormalizedLiteratureRecordModel)
    )
    snapshot_count = session.scalar(select(func.count()).select_from(AnalysisSnapshotModel))
    trial_enrichment_count = session.scalar(
        select(func.count()).select_from(TrialLLMEnrichmentModel)
    )
    literature_enrichment_count = session.scalar(
        select(func.count()).select_from(LiteratureLLMEnrichmentModel)
    )

    assert bundle.global_stats.total_trial_count == 1
    assert bundle.global_stats.total_literature_count == 1
    assert bundle.section_inputs.pipeline_overview.trial_keys == ["NCT03188393"]
    assert bundle.section_inputs.research_update.literature_keys == ["12345678"]
    assert bundle.llm_enrichment_summary.trial_total == 1
    assert bundle.llm_enrichment_summary.trial_succeeded == 0
    assert bundle.llm_enrichment_summary.warning_count == 1
    assert any(item.code == "llm_enrichment_disabled" for item in bundle.warnings)
    assert normalized_trial_count == 1
    assert normalized_literature_count == 1
    assert snapshot_count == 1
    assert trial_enrichment_count == 0
    assert literature_enrichment_count == 0

    session.close()


def test_analysis_pipeline_keeps_best_effort_when_one_llm_record_fails() -> None:
    initialize_database()
    session = SessionLocal()
    _clear_tables(session)
    fetch_run_id = _seed_fetch_run(session)

    bundle = AnalysisPipelineService(
        session,
        llm_client=StubLLMClient(
            responses=[
                {
                    "dimension_insights": {
                        "target_overview": {
                            "can_contribute": True,
                            "relevance_score": 88,
                            "confidence": 72,
                            "summary": "Target relevant trial.",
                            "key_points": ["Mentions HER2 and breast cancer."],
                            "evidence_snippets": [],
                        },
                        "pipeline_overview": {
                            "can_contribute": True,
                            "relevance_score": 90,
                            "confidence": 81,
                            "summary": "Active phase 2 pipeline asset.",
                            "key_points": ["Recruiting phase 2 study."],
                            "evidence_snippets": [],
                        },
                        "research_update": {
                            "can_contribute": False,
                            "relevance_score": 35,
                            "confidence": 64,
                            "summary": "Limited direct recency insight.",
                            "key_points": [],
                            "evidence_snippets": [],
                        },
                        "competition_assessment": {
                            "can_contribute": True,
                            "relevance_score": 79,
                            "confidence": 75,
                            "summary": "Sponsor and phase are useful for competition.",
                            "key_points": ["Sponsor identified."],
                            "evidence_snippets": [],
                        },
                    },
                    "llm_scores": {
                        "target_overview": 86,
                        "pipeline_overview": 92,
                        "research_update": 30,
                        "competition_assessment": 80,
                        "overall_score": 77,
                    },
                    "modality": "drug",
                    "asset_candidates": ["Example Drug"],
                    "company_candidates": ["Example Sponsor"],
                    "risk_signals": ["No published results yet."],
                    "opportunity_signals": ["Recruiting phase 2 study."],
                },
                RuntimeError("synthetic LLM failure"),
            ]
        ),
        llm_model="test-model",
    ).build(fetch_run_id)

    trial_enrichment_count = session.scalar(
        select(func.count()).select_from(TrialLLMEnrichmentModel)
    )
    literature_enrichment_count = session.scalar(
        select(func.count()).select_from(LiteratureLLMEnrichmentModel)
    )

    assert bundle.llm_enrichment_summary.trial_succeeded == 1
    assert bundle.llm_enrichment_summary.literature_succeeded == 0
    assert bundle.llm_enrichment_summary.warning_count == 1
    assert bundle.llm_enrichment_summary.model == "test-model"
    assert bundle.trial_llm_enrichments[0].trial_key == "NCT03188393"
    assert any(item.code == "literature_llm_enrichment_failed" for item in bundle.warnings)
    assert trial_enrichment_count == 1
    assert literature_enrichment_count == 0

    session.close()


class StubLLMClient:
    def __init__(self, *, responses: list[dict | Exception]) -> None:
        self.responses = responses

    def generate_structured(self, **kwargs):
        response_model = kwargs["response_model"]
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response_model.model_validate(response)


def _seed_fetch_run(session) -> str:
    fetch_run = FetchRunRepository(session).create(
        TargetQuery(target="HER2", indication="breast cancer", aliases=["ERBB2"])
    )
    raw_repository = RawRecordRepository(session)
    raw_repository.create_many(
        [
            RawRecord(
                fetch_run_id=fetch_run.fetch_run_id,
                source_name=SourceName.CLINICALTRIALS,
                source_id="NCT03188393",
                source_url="https://clinicaltrials.gov/study/NCT03188393",
                target="HER2",
                indication="breast cancer",
                payload={
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT03188393",
                            "briefTitle": "HER2 Trial",
                        },
                        "statusModule": {
                            "overallStatus": "RECRUITING",
                            "studyFirstPostDateStruct": {"date": "2024-01-01"},
                        },
                        "descriptionModule": {
                            "briefSummary": "A study for HER2-positive breast cancer.",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Example Sponsor"},
                        },
                        "conditionsModule": {
                            "conditions": ["Breast Cancer"],
                            "keywords": ["HER2"],
                        },
                        "designModule": {
                            "studyType": "INTERVENTIONAL",
                            "phases": ["PHASE2"],
                        },
                        "armsInterventionsModule": {
                            "interventions": [{"type": "DRUG", "name": "Example Drug"}]
                        },
                    },
                    "derivedSection": {
                        "conditionBrowseModule": {"meshes": [{"term": "Breast Neoplasms"}]}
                    },
                },
                query_snapshot={"source": "clinicaltrials"},
                retrieved_at=datetime.now(timezone.utc),
            ),
            RawRecord(
                fetch_run_id=fetch_run.fetch_run_id,
                source_name=SourceName.PUBMED,
                source_id="12345678",
                source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
                target="HER2",
                indication="breast cancer",
                payload={"xml": PUBMED_XML},
                query_snapshot={"source": "pubmed"},
                retrieved_at=datetime.now(timezone.utc),
            ),
        ]
    )
    return fetch_run.fetch_run_id


def _clear_tables(session) -> None:
    session.execute(delete(AnalysisSnapshotModel))
    session.execute(delete(LiteratureLLMEnrichmentModel))
    session.execute(delete(TrialLLMEnrichmentModel))
    session.execute(delete(NormalizedLiteratureRecordModel))
    session.execute(delete(NormalizedTrialRecordModel))
    session.execute(delete(FetchRunRawRecordModel))
    session.execute(delete(RawRecordModel))
    session.execute(delete(FetchRunModel))
    session.commit()
