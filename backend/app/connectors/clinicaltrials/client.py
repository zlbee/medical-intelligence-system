from __future__ import annotations

import httpx

from app.infra.settings import Settings


class ClinicalTrialsGovClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search_studies(self, client: httpx.Client, params: dict[str, str]) -> httpx.Response:
        response = client.get(
            f"{self.settings.clinicaltrials_base_url}/studies",
            params=params,
        )
        response.raise_for_status()
        return response

