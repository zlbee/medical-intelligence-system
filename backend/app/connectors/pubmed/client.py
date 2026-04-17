from __future__ import annotations

import httpx

from app.infra.settings import Settings


class PubMedClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def esearch(self, client: httpx.Client, params: dict[str, str]) -> httpx.Response:
        response = client.get(self.settings.pubmed_esearch_url, params=params)
        response.raise_for_status()
        return response

    def efetch(self, client: httpx.Client, params: dict[str, str]) -> httpx.Response:
        response = client.get(self.settings.pubmed_efetch_url, params=params)
        response.raise_for_status()
        return response

