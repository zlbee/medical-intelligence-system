import httpx

from app.connectors.pubmed import PubMedConnector
from app.domain import TargetQuery
from app.infra.settings import Settings


PUBMED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <ArticleTitle>HER2 targeted therapy study</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_pubmed_connector_supports_json_filter_config() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            term = request.url.params["term"]
            assert '"HER2"[Title/Abstract]' in term
            assert '"ERBB2"[Title/Abstract]' in term
            assert '"Clinical Trial"[Publication Type]' in term
            assert '("2023/01/01"[Date - Publication] : "2024/12/31"[Date - Publication])' in term
            return httpx.Response(
                200,
                json={"esearchresult": {"count": "1", "idlist": ["12345"]}},
            )

        return httpx.Response(200, text=PUBMED_XML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(
        pubmed_esearch_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        pubmed_efetch_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
    )
    connector = PubMedConnector(settings=settings, http_client=client)
    query = TargetQuery.model_validate(
        {
            "target": "HER2",
            "aliases": ["ERBB2"],
            "source_configs": {
                "pubmed": {
                    "retmax": 5,
                    "filters": {
                        "publication_types": ["Clinical Trial"],
                        "date_from": "2023/01/01",
                        "date_to": "2024/12/31",
                    },
                }
            },
        }
    )

    result = connector.search(query, fetch_run_id="fetch-1")

    assert result.total_count == 1
    assert len(result.raw_records) == 1
    assert result.raw_records[0].source_id == "12345"
    assert "HER2 targeted therapy study" in result.raw_records[0].payload["xml"]

