from __future__ import annotations

from datetime import datetime, timezone

from app.domain import RawRecord, SourceName
from app.normalize import LiteratureNormalizer


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
        <AbstractText Label="BACKGROUND">HER2 therapy background.</AbstractText>
        <AbstractText Label="RESULTS">NCT03188393 showed activity.</AbstractText>
      </Abstract>
      <AuthorList>
        <Author ValidYN="Y">
          <LastName>Li</LastName>
          <ForeName>Huan</ForeName>
          <Initials>H</Initials>
          <AffiliationInfo>
            <Affiliation>Example University</Affiliation>
          </AffiliationInfo>
        </Author>
      </AuthorList>
      <GrantList CompleteYN="Y">
        <Grant>
          <GrantID>U10 CA180822</GrantID>
          <Acronym>CA</Acronym>
          <Agency>NCI NIH HHS</Agency>
          <Country>United States</Country>
        </Grant>
      </GrantList>
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
        <PublicationType>Journal Article</PublicationType>
      </PublicationTypeList>
    </Article>
    <MeshHeadingList>
      <MeshHeading>
        <DescriptorName>Breast Neoplasms</DescriptorName>
      </MeshHeading>
    </MeshHeadingList>
    <KeywordList>
      <Keyword>HER2</Keyword>
      <Keyword>ERBB2</Keyword>
    </KeywordList>
    <CommentsCorrectionsList>
      <CommentsCorrections RefType="CommentIn">
        <RefSource>JAMA Surg. 2025;160(7):731-732.</RefSource>
        <PMID Version="1">87654321</PMID>
      </CommentsCorrections>
    </CommentsCorrectionsList>
  </MedlineCitation>
</PubmedArticle>
""".strip()


def test_literature_normalizer_maps_rich_pubmed_metadata() -> None:
    normalizer = LiteratureNormalizer()
    record = RawRecord(
        fetch_run_id="fetch-1",
        source_name=SourceName.PUBMED,
        source_id="12345678",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        target="HER2",
        indication="breast cancer",
        payload={"xml": PUBMED_XML},
        query_snapshot={"source": "pubmed"},
        retrieved_at=datetime.now(timezone.utc),
    )

    normalized = normalizer.normalize(record)

    assert normalized.literature_key == "12345678"
    assert normalized.doi == "10.1000/example"
    assert normalized.title == "HER2-targeted therapy update."
    assert normalized.journal == "Clinical Cancer Research"
    assert normalized.publication_types == ["Clinical Trial", "Journal Article"]
    assert normalized.mesh_terms == ["Breast Neoplasms"]
    assert normalized.keywords == ["HER2", "ERBB2"]
    assert normalized.affiliations == ["Example University"]
    assert normalized.grants[0].grant_id == "U10 CA180822"
    assert normalized.databanks[0].accession_numbers == ["NCT03188393"]
    assert normalized.linked_nct_ids == ["NCT03188393"]
    assert normalized.related_pmids == ["87654321"]
