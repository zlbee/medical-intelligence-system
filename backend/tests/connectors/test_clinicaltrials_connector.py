import httpx

from app.connectors.clinicaltrials import ClinicalTrialsGovConnector
from app.domain import TargetQuery
from app.infra.settings import Settings


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

