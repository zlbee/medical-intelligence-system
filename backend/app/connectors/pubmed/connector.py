from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.pubmed.client import PubMedClient
from app.domain import ConnectorResult, RawRecord, SourceName, TargetQuery


class PubMedConnector(BaseConnector):
    source_name = SourceName.PUBMED

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.client = PubMedClient(self.settings)

    def search(self, query: TargetQuery, *, fetch_run_id: str) -> ConnectorResult:
        config = query.source_configs.pubmed
        term = self._build_term(query)
        esearch_params = self._build_esearch_params(query, term)
        raw_records: list[RawRecord] = []

        started = time.perf_counter()
        with self.client_context() as http_client:
            esearch_response = self.client.esearch(http_client, esearch_params)
            esearch_payload = esearch_response.json()
            search_result = esearch_payload.get("esearchresult", {})
            id_list = list(search_result.get("idlist", []))
            total_count = self._safe_int(search_result.get("count"))

            for batch_index, batch_ids in enumerate(
                self._chunked(id_list, config.batch_size)
            ):
                efetch_params = self._build_efetch_params(batch_ids)
                efetch_response = self.client.efetch(http_client, efetch_params)
                articles = self._extract_articles(efetch_response.text)

                request_snapshot = {
                    "batch_index": batch_index,
                    "term": term,
                    "esearch_params": esearch_params,
                    "efetch_params": efetch_params,
                    "batch_ids": batch_ids,
                }
                for article_index, article in enumerate(articles):
                    source_id = self._extract_pmid(article, article_index, batch_index)
                    article_xml = ET.tostring(article, encoding="unicode")
                    raw_records.append(
                        RawRecord(
                            fetch_run_id=fetch_run_id,
                            source_name=self.source_name,
                            source_id=source_id,
                            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{source_id}/",
                            target=query.target,
                            indication=query.indication,
                            payload={"xml": article_xml},
                            query_snapshot=request_snapshot,
                        )
                    )

        elapsed_ms = (time.perf_counter() - started) * 1000
        return ConnectorResult(
            source_name=self.source_name,
            raw_records=raw_records,
            total_count=total_count,
            elapsed_ms=elapsed_ms,
            request_snapshot={
                "term": term,
                "esearch_params": esearch_params,
                "efetch_batch_size": config.batch_size,
            },
        )

    def _build_term(self, query: TargetQuery) -> str:
        config = query.source_configs.pubmed
        if config.term:
            return config.term

        filters = config.filters
        clauses: list[str] = []

        target_terms = [query.target, *query.aliases]
        target_fragments = [
            f'"{term}"[Title/Abstract]'
            for term in dict.fromkeys(item.strip() for item in target_terms if item.strip())
        ]
        if target_fragments:
            clauses.append(f"({' OR '.join(target_fragments)})")

        if query.indication:
            clauses.append(f'("{query.indication}"[Title/Abstract])')

        clauses.extend(
            f'"{term}"[Publication Type]' for term in filters.publication_types
        )
        clauses.extend(f'"{term}"[Journal]' for term in filters.journals)
        clauses.extend(f'"{term}"[Author]' for term in filters.authors)
        clauses.extend(f'"{term}"[MeSH Terms]' for term in filters.mesh_terms)
        clauses.extend(
            f'"{term}"[Title/Abstract]' for term in filters.title_abstract_terms
        )
        clauses.extend(filters.extra_terms)

        if filters.has_abstract is True:
            clauses.append("hasabstract[text]")
        if filters.date_from or filters.date_to:
            start = filters.date_from or "1000/01/01"
            end = filters.date_to or "3000/12/31"
            clauses.append(f'("{start}"[Date - Publication] : "{end}"[Date - Publication])')

        return " AND ".join(clauses) if clauses else query.target

    def _build_esearch_params(
        self,
        query: TargetQuery,
        term: str,
    ) -> dict[str, str]:
        config = query.source_configs.pubmed
        params: dict[str, str] = {
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "retmax": str(config.retmax),
            "retstart": str(config.retstart),
            "sort": config.sort,
            "tool": self.settings.ncbi_tool,
        }
        if self.settings.ncbi_email:
            params["email"] = self.settings.ncbi_email
        if self.settings.ncbi_api_key:
            params["api_key"] = self.settings.ncbi_api_key

        for key, value in config.esearch_params.items():
            params[key] = self._serialize_value(value)

        return params

    def _build_efetch_params(self, ids: list[str]) -> dict[str, str]:
        params: dict[str, str] = {
            "db": "pubmed",
            "retmode": "xml",
            "id": ",".join(ids),
            "tool": self.settings.ncbi_tool,
        }
        if self.settings.ncbi_email:
            params["email"] = self.settings.ncbi_email
        if self.settings.ncbi_api_key:
            params["api_key"] = self.settings.ncbi_api_key
        return params

    def _extract_articles(self, xml_text: str) -> list[ET.Element]:
        root = ET.fromstring(xml_text)
        articles = list(root.findall("PubmedArticle"))
        book_articles = list(root.findall("PubmedBookArticle"))
        return articles + book_articles

    def _extract_pmid(self, article: ET.Element, article_index: int, batch_index: int) -> str:
        pmid_node = article.find("./MedlineCitation/PMID")
        if pmid_node is None:
            pmid_node = article.find(".//PMID")
        if pmid_node is not None and pmid_node.text:
            return pmid_node.text.strip()
        return f"pubmed-{batch_index}-{article_index}"

    def _serialize_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)

    def _safe_int(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _chunked(self, items: list[str], chunk_size: int) -> list[list[str]]:
        return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]
