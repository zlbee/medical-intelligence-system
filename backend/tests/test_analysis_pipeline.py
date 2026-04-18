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


def test_analysis_pipeline_can_limit_llm_enrichment_to_rule_score_top_n() -> None:
    initialize_database()
    session = SessionLocal()
    _clear_tables(session)
    fetch_run_id = _seed_fetch_run_with_multiple_records(session)

    bundle = AnalysisPipelineService(
        session,
        llm_client=StubLLMClient(
            responses=[
                _trial_llm_response(summary="Top-ranked HER2 trial."),
                _literature_llm_response(summary="Top-ranked HER2 paper."),
            ]
        ),
        llm_model="test-model",
        llm_enrichment_full_scan=False,
        llm_enrichment_top_n=1,
    ).build(fetch_run_id)

    assert bundle.llm_enrichment_summary.trial_total == 2
    assert bundle.llm_enrichment_summary.trial_succeeded == 1
    assert bundle.llm_enrichment_summary.literature_total == 2
    assert bundle.llm_enrichment_summary.literature_succeeded == 1
    assert [item.trial_key for item in bundle.trial_llm_enrichments] == ["NCT03188393"]
    assert [item.literature_key for item in bundle.literature_llm_enrichments] == ["12345678"]
    assert any(item.code == "llm_enrichment_top_n_applied" for item in bundle.warnings)

    session.close()


def test_analysis_pipeline_can_skip_llm_when_selective_top_n_is_zero() -> None:
    initialize_database()
    session = SessionLocal()
    _clear_tables(session)
    fetch_run_id = _seed_fetch_run(session)

    bundle = AnalysisPipelineService(
        session,
        llm_client=StubLLMClient(responses=[]),
        llm_model="test-model",
        llm_enrichment_full_scan=False,
        llm_enrichment_top_n=0,
    ).build(fetch_run_id)

    assert bundle.llm_enrichment_summary.trial_succeeded == 0
    assert bundle.llm_enrichment_summary.literature_succeeded == 0
    assert any(item.code == "llm_enrichment_top_n_zero" for item in bundle.warnings)

    session.close()


def test_analysis_pipeline_reuses_cached_stage2_results_across_fetch_runs() -> None:
    initialize_database()
    session = SessionLocal()
    _clear_tables(session)
    first_fetch_run_id = _seed_fetch_run(session)
    AnalysisPipelineService(
        session,
        llm_client=StubLLMClient(
            responses=[
                _trial_llm_response(summary="Cached trial enrichment."),
                _literature_llm_response(summary="Cached literature enrichment."),
            ]
        ),
        llm_model="test-model",
    ).build(first_fetch_run_id)

    second_fetch_run_id = _seed_fetch_run(session)
    trial_normalizer = CountingTrialNormalizer()
    literature_normalizer = CountingLiteratureNormalizer()
    service = AnalysisPipelineService(
        session,
        llm_client=FailingLLMClient(),
        llm_model="test-model",
    )
    service.trial_normalizer = trial_normalizer
    service.literature_normalizer = literature_normalizer

    bundle = service.build(second_fetch_run_id)
    normalized_trials = service.list_normalized_trials(second_fetch_run_id)
    normalized_literature = service.list_normalized_literature(second_fetch_run_id)
    trial_enrichments = service.trial_llm_enrichment_repository.list_by_fetch_run(
        second_fetch_run_id
    )
    literature_enrichments = service.literature_llm_enrichment_repository.list_by_fetch_run(
        second_fetch_run_id
    )

    assert trial_normalizer.normalize_many_calls == 0
    assert trial_normalizer.normalize_calls == 0
    assert literature_normalizer.normalize_many_calls == 0
    assert literature_normalizer.normalize_calls == 0
    assert bundle.llm_enrichment_summary.trial_succeeded == 1
    assert bundle.llm_enrichment_summary.literature_succeeded == 1
    assert normalized_trials[0].source_traces[0].fetch_run_id == second_fetch_run_id
    assert normalized_literature[0].source_traces[0].fetch_run_id == second_fetch_run_id
    assert trial_enrichments[0].fetch_run_id == second_fetch_run_id
    assert literature_enrichments[0].fetch_run_id == second_fetch_run_id

    session.close()


def test_analysis_pipeline_reuses_cached_enrichments_outside_top_n() -> None:
    initialize_database()
    session = SessionLocal()
    _clear_tables(session)
    first_fetch_run_id = _seed_fetch_run_with_multiple_records(session)
    AnalysisPipelineService(
        session,
        llm_client=StubLLMClient(
            responses=[
                _trial_llm_response(summary="Cached primary trial."),
                _trial_llm_response(summary="Cached secondary trial."),
                _literature_llm_response(summary="Cached primary paper."),
                _literature_llm_response(summary="Cached secondary paper."),
            ]
        ),
        llm_model="test-model",
    ).build(first_fetch_run_id)

    second_fetch_run_id = _seed_fetch_run_with_multiple_records(session)
    service = AnalysisPipelineService(
        session,
        llm_client=FailingLLMClient(),
        llm_model="test-model",
        llm_enrichment_full_scan=False,
        llm_enrichment_top_n=1,
    )

    bundle = service.build(second_fetch_run_id)

    assert bundle.llm_enrichment_summary.trial_succeeded == 2
    assert bundle.llm_enrichment_summary.literature_succeeded == 2
    assert {item.trial_key for item in bundle.trial_llm_enrichments} == {
        "NCT03188393",
        "NCT09999999",
    }
    assert {item.literature_key for item in bundle.literature_llm_enrichments} == {
        "12345678",
        "87654321",
    }
    assert any(item.code == "llm_enrichment_top_n_applied" for item in bundle.warnings)

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


class FailingLLMClient:
    def generate_structured(self, **kwargs):
        raise AssertionError("LLM should not be called when cache reuse is working.")


class CountingTrialNormalizer:
    def __init__(self) -> None:
        from app.normalize import TrialNormalizer

        self._delegate = TrialNormalizer()
        self.normalize_many_calls = 0
        self.normalize_calls = 0

    def normalize_many(self, records):
        self.normalize_many_calls += 1
        return self._delegate.normalize_many(records)

    def normalize(self, record):
        self.normalize_calls += 1
        return self._delegate.normalize(record)

    def extract_trial_key(self, record):
        return self._delegate.extract_trial_key(record)

    def build_source_trace(self, record):
        return self._delegate.build_source_trace(record)


class CountingLiteratureNormalizer:
    def __init__(self) -> None:
        from app.normalize import LiteratureNormalizer

        self._delegate = LiteratureNormalizer()
        self.normalize_many_calls = 0
        self.normalize_calls = 0

    def normalize_many(self, records):
        self.normalize_many_calls += 1
        return self._delegate.normalize_many(records)

    def normalize(self, record):
        self.normalize_calls += 1
        return self._delegate.normalize(record)

    def extract_literature_key(self, record):
        return self._delegate.extract_literature_key(record)

    def build_source_trace(self, record):
        return self._delegate.build_source_trace(record)


def _trial_llm_response(*, summary: str) -> dict:
    return {
        "dimension_insights": {
            "target_overview": {
                "can_contribute": True,
                "relevance_score": 88,
                "confidence": 72,
                "summary": summary,
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
    }


def _literature_llm_response(*, summary: str) -> dict:
    return {
        "dimension_insights": {
            "target_overview": {
                "can_contribute": True,
                "relevance_score": 88,
                "confidence": 72,
                "summary": summary,
                "key_points": ["Summarizes HER2-targeted therapy."],
                "evidence_snippets": [],
            },
            "pipeline_overview": {
                "can_contribute": False,
                "relevance_score": 40,
                "confidence": 65,
                "summary": "Secondary pipeline context only.",
                "key_points": [],
                "evidence_snippets": [],
            },
            "research_update": {
                "can_contribute": True,
                "relevance_score": 95,
                "confidence": 88,
                "summary": "Recent and strong study update.",
                "key_points": ["Recent publication with NCT linkage."],
                "evidence_snippets": [],
            },
            "competition_assessment": {
                "can_contribute": True,
                "relevance_score": 76,
                "confidence": 71,
                "summary": "Useful competitive readout.",
                "key_points": ["Contains trial linkage."],
                "evidence_snippets": [],
            },
        },
        "llm_scores": {
            "target_overview": 89,
            "pipeline_overview": 35,
            "research_update": 93,
            "competition_assessment": 74,
            "overall_score": 78,
        },
        "study_design": "Clinical Trial",
        "mechanism_themes": ["HER2 targeting"],
        "efficacy_signals": ["Promising efficacy signal."],
        "safety_signals": ["Manageable safety profile."],
        "trial_link_hints": ["NCT03188393"],
    }


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


def _seed_fetch_run_with_multiple_records(session) -> str:
    fetch_run_id = _seed_fetch_run(session)
    RawRecordRepository(session).create_many(
        [
            RawRecord(
                fetch_run_id=fetch_run_id,
                source_name=SourceName.CLINICALTRIALS,
                source_id="NCT09999999",
                source_url="https://clinicaltrials.gov/study/NCT09999999",
                target="HER2",
                indication="breast cancer",
                payload={
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT09999999",
                            "briefTitle": "General solid tumor study",
                        },
                        "statusModule": {
                            "overallStatus": "ACTIVE_NOT_RECRUITING",
                            "studyFirstPostDateStruct": {"date": "2022-01-01"},
                        },
                        "descriptionModule": {
                            "briefSummary": "A general oncology study without direct HER2 focus.",
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {"name": "Other Sponsor"},
                        },
                        "conditionsModule": {
                            "conditions": ["Solid Tumor"],
                            "keywords": ["oncology"],
                        },
                        "designModule": {
                            "studyType": "INTERVENTIONAL",
                            "phases": ["PHASE1"],
                        },
                        "armsInterventionsModule": {
                            "interventions": [{"type": "DRUG", "name": "Other Drug"}]
                        },
                    }
                },
                query_snapshot={"source": "clinicaltrials"},
                retrieved_at=datetime.now(timezone.utc),
            ),
            RawRecord(
                fetch_run_id=fetch_run_id,
                source_name=SourceName.PUBMED,
                source_id="87654321",
                source_url="https://pubmed.ncbi.nlm.nih.gov/87654321/",
                target="HER2",
                indication="breast cancer",
                payload={
                    "xml": """
<PubmedArticle>
  <MedlineCitation>
    <PMID Version=\"1\">87654321</PMID>
    <Article>
      <Journal>
        <JournalIssue>
          <PubDate>
            <Year>2021</Year>
            <Month>Jan</Month>
            <Day>01</Day>
          </PubDate>
        </JournalIssue>
        <Title>General Oncology Journal</Title>
      </Journal>
      <ArticleTitle>General oncology update.</ArticleTitle>
      <Abstract>
        <AbstractText>A broad oncology review without HER2-specific findings.</AbstractText>
      </Abstract>
      <PublicationTypeList>
        <PublicationType>Review</PublicationType>
      </PublicationTypeList>
    </Article>
  </MedlineCitation>
</PubmedArticle>
""".strip()
                },
                query_snapshot={"source": "pubmed"},
                retrieved_at=datetime.now(timezone.utc),
            ),
        ]
    )
    return fetch_run_id


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
