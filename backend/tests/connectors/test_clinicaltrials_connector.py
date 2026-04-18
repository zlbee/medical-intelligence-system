import httpx

from app.connectors.clinicaltrials import ClinicalTrialsGovConnector
from app.domain import TargetQuery
from app.infra.settings import Settings


def _build_studies(prefix: str, count: int) -> list[dict]:
    return [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": f"NCT{prefix}{index:05d}",
                    "briefTitle": f"Study {prefix}-{index}",
                }
            }
        }
        for index in range(count)
    ]


def test_clinicaltrials_connector_supports_json_filter_config() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query.term"] == "HER2 OR ERBB2"
        assert request.url.params["query.cond"] == "breast cancer"
        assert request.url.params["filter.overallStatus"] == "RECRUITING,ACTIVE_NOT_RECRUITING"
        assert request.url.params["pageSize"] == "5"
        return httpx.Response(
            200,
            json={
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT00000001",
                                "briefTitle": "HER2 antibody study",
                            }
                        }
                    }
                ],
                "totalCount": 1,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(clinicaltrials_base_url="https://clinicaltrials.gov/api/v2")
    connector = ClinicalTrialsGovConnector(settings=settings, http_client=client)
    query = TargetQuery.model_validate(
        {
            "target": "HER2",
            "aliases": ["ERBB2"],
            "indication": "breast cancer",
            "source_configs": {
                "clinicaltrials": {
                    "page_size": 5,
                    "filters": {
                        "overallStatus": [
                            "RECRUITING",
                            "ACTIVE_NOT_RECRUITING",
                        ]
                    },
                }
            },
        }
    )

    result = connector.search(query, fetch_run_id="fetch-1")

    assert result.total_count == 1
    assert len(result.raw_records) == 1
    assert result.raw_records[0].source_id == "NCT00000001"
    assert result.raw_records[0].payload["protocolSection"]["identificationModule"]["briefTitle"] == "HER2 antibody study"
    assert result.request_snapshot["applied_record_cap"] == 100
    assert result.request_snapshot["stop_reason"] == "no_next_page_token"


def test_clinicaltrials_connector_fetches_multiple_pages_until_record_cap() -> None:
    seen_tokens: list[str | None] = []
    sleep_calls: list[float] = []
    pages = {
        None: {
            "studies": _build_studies("1", 10),
            "nextPageToken": "page-2",
            "totalCount": 200,
        },
        "page-2": {
            "studies": _build_studies("2", 10),
            "nextPageToken": "page-3",
            "totalCount": 200,
        },
        "page-3": {
            "studies": _build_studies("3", 10),
            "nextPageToken": "page-4",
            "totalCount": 200,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        seen_tokens.append(token)
        payload = pages[token]
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(
        clinicaltrials_base_url="https://clinicaltrials.gov/api/v2",
        fetch_clinicaltrials_max_records=25,
        fetch_query_interval_seconds=0.5,
    )
    connector = ClinicalTrialsGovConnector(
        settings=settings,
        http_client=client,
        sleep_fn=sleep_calls.append,
    )
    query = TargetQuery.model_validate(
        {
            "target": "HER2",
            "source_configs": {
                "clinicaltrials": {
                    "page_size": 10,
                }
            },
        }
    )

    result = connector.search(query, fetch_run_id="fetch-1")

    assert seen_tokens == [None, "page-2", "page-3"]
    assert sleep_calls == [0.5, 0.5]
    assert result.total_count == 200
    assert len(result.raw_records) == 30
    assert result.request_snapshot["applied_record_cap"] == 25
    assert result.request_snapshot["stop_reason"] == "record_cap_reached"
    assert len(result.request_snapshot["pages"]) == 3


def test_clinicaltrials_connector_stops_when_page_is_empty() -> None:
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        if token is None:
            return httpx.Response(
                200,
                json={
                    "studies": _build_studies("1", 2),
                    "nextPageToken": "page-2",
                    "totalCount": 2,
                },
            )
        return httpx.Response(
            200,
            json={"studies": [], "nextPageToken": "page-3", "totalCount": 2},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(
        clinicaltrials_base_url="https://clinicaltrials.gov/api/v2",
        fetch_query_interval_seconds=0.5,
    )
    connector = ClinicalTrialsGovConnector(
        settings=settings,
        http_client=client,
        sleep_fn=sleep_calls.append,
    )

    result = connector.search(TargetQuery(target="HER2"), fetch_run_id="fetch-1")

    assert len(result.raw_records) == 2
    assert sleep_calls == [0.5]
    assert result.request_snapshot["stop_reason"] == "empty_page"

