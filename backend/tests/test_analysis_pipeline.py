from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy import delete

from app.domain import RawRecord, SourceName, TargetQuery
from app.infra.db import SessionLocal, initialize_database
from app.orchestration import AnalysisPipelineService
from app.repository import FetchRunRepository, RawRecordRepository
from app.repository.models import (
    AnalysisSnapshotModel,
    FetchRunModel,
    FetchRunRawRecordModel,
    NormalizedLiteratureRecordModel,
    NormalizedTrialRecordModel,
    RawRecordModel,
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


def test_analysis_pipeline_builds_and_persists_bundle() -> None:
    initialize_database()
    session = SessionLocal()
    _clear_tables(session)

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
                            "interventions": [
                                {"type": "DRUG", "name": "Example Drug"}
                            ]
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

    bundle = AnalysisPipelineService(session).build(fetch_run.fetch_run_id)

    normalized_trial_count = session.scalar(
        select(func.count()).select_from(NormalizedTrialRecordModel)
    )
    normalized_literature_count = session.scalar(
        select(func.count()).select_from(NormalizedLiteratureRecordModel)
    )
    snapshot_count = session.scalar(select(func.count()).select_from(AnalysisSnapshotModel))

    assert bundle.global_stats.total_trial_count == 1
    assert bundle.global_stats.total_literature_count == 1
    assert bundle.section_inputs.pipeline_overview.trial_keys == ["NCT03188393"]
    assert bundle.section_inputs.research_update.literature_keys == ["12345678"]
    assert normalized_trial_count == 1
    assert normalized_literature_count == 1
    assert snapshot_count == 1

    session.close()


def _clear_tables(session) -> None:
    session.execute(delete(AnalysisSnapshotModel))
    session.execute(delete(NormalizedLiteratureRecordModel))
    session.execute(delete(NormalizedTrialRecordModel))
    session.execute(delete(FetchRunRawRecordModel))
    session.execute(delete(RawRecordModel))
    session.execute(delete(FetchRunModel))
    session.commit()
