from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from collections.abc import Iterator

import httpx

from app.domain import ConnectorResult, TargetQuery
from app.infra.http import build_http_client
from app.infra.settings import Settings, get_settings


class BaseConnector(ABC):
    source_name: str

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client

    @abstractmethod
    def search(self, query: TargetQuery, *, fetch_run_id: str) -> ConnectorResult:
        raise NotImplementedError

    @contextmanager
    def client_context(self) -> Iterator[httpx.Client]:
        if self.http_client is not None:
            yield self.http_client
            return

        with build_http_client(self.settings) as client:
            yield client

