import httpx

from app.connectors.pubmed import PubMedConnector
from app.domain import TargetQuery
from app.infra.settings import Settings


def _build_pubmed_xml(ids: list[str]) -> str:
    articles = "\n".join(
        f"""
  <PubmedArticle>
    <MedlineCitation>
      <PMID>{pmid}</PMID>
      <Article>
        <ArticleTitle>Study {pmid}</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
""".rstrip()
        for pmid in ids
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
{articles}
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

        return httpx.Response(200, text=_build_pubmed_xml(["12345"]))

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
    assert "Study 12345" in result.raw_records[0].payload["xml"]
    assert result.request_snapshot["applied_record_cap"] == 100
    assert result.request_snapshot["stop_reason"] == "retstart_exhausted_total_count"


def test_pubmed_connector_fetches_multiple_rounds_until_record_cap() -> None:
    observed_retstarts: list[str] = []
    observed_efetch_sizes: list[int] = []
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            retstart = request.url.params["retstart"]
            observed_retstarts.append(retstart)
            start = int(retstart)
            ids = [str(start + index + 1) for index in range(10)]
            return httpx.Response(
                200,
                json={
                    "esearchresult": {
                        "count": "100",
                        "idlist": ids,
                    }
                },
            )

        batch_ids = request.url.params["id"].split(",")
        observed_efetch_sizes.append(len(batch_ids))
        return httpx.Response(200, text=_build_pubmed_xml(batch_ids))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(
        pubmed_esearch_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        pubmed_efetch_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        fetch_pubmed_max_records=25,
        fetch_query_interval_seconds=0.5,
    )
    connector = PubMedConnector(
        settings=settings,
        http_client=client,
        sleep_fn=sleep_calls.append,
    )
    query = TargetQuery.model_validate(
        {
            "target": "HER2",
            "source_configs": {
                "pubmed": {
                    "retmax": 10,
                    "batch_size": 4,
                }
            },
        }
    )

    result = connector.search(query, fetch_run_id="fetch-1")

    assert observed_retstarts == ["0", "10", "20"]
    assert observed_efetch_sizes == [4, 4, 2, 4, 4, 2, 4, 4, 2]
    assert sleep_calls == [0.5, 0.5]
    assert len(result.raw_records) == 30
    assert result.request_snapshot["stop_reason"] == "record_cap_reached"
    assert len(result.request_snapshot["rounds"]) == 3
    assert result.request_snapshot["rounds"][0]["efetch_batches"][0]["batch_ids"] == [
        "1",
        "2",
        "3",
        "4",
    ]


def test_pubmed_connector_stops_when_total_count_is_exhausted() -> None:
    observed_retstarts: list[str] = []
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            retstart = request.url.params["retstart"]
            observed_retstarts.append(retstart)
            if retstart == "0":
                ids = [str(index + 1) for index in range(10)]
            else:
                ids = [str(index + 11) for index in range(5)]
            return httpx.Response(
                200,
                json={"esearchresult": {"count": "15", "idlist": ids}},
            )

        batch_ids = request.url.params["id"].split(",")
        return httpx.Response(200, text=_build_pubmed_xml(batch_ids))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(
        pubmed_esearch_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        pubmed_efetch_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        fetch_query_interval_seconds=0.5,
    )
    connector = PubMedConnector(
        settings=settings,
        http_client=client,
        sleep_fn=sleep_calls.append,
    )
    query = TargetQuery.model_validate(
        {
            "target": "HER2",
            "source_configs": {
                "pubmed": {
                    "retmax": 10,
                    "batch_size": 10,
                }
            },
        }
    )

    result = connector.search(query, fetch_run_id="fetch-1")

    assert observed_retstarts == ["0", "10"]
    assert sleep_calls == [0.5]
    assert len(result.raw_records) == 15
    assert result.request_snapshot["stop_reason"] == "retstart_exhausted_total_count"

