from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from app.domain import (
    AbstractSection,
    AuthorRef,
    DatabankRef,
    GrantRef,
    NormalizedLiteratureRecord,
    RawRecord,
    SourceName,
    SourceTrace,
)
from app.normalize.common import (
    build_structured_date,
    clean_text,
    extract_nct_ids,
    unique_strings,
)


class LiteratureNormalizer:
    """Maps PubMed XML payloads into a stable literature domain object."""

    def normalize_many(self, records: list[RawRecord]) -> list[NormalizedLiteratureRecord]:
        normalized_by_key: dict[str, NormalizedLiteratureRecord] = {}
        for record in records:
            if record.source_name != SourceName.PUBMED:
                continue

            normalized = self.normalize(record)
            existing = normalized_by_key.get(normalized.literature_key)
            if existing is None:
                normalized_by_key[normalized.literature_key] = normalized
                continue
            normalized_by_key[normalized.literature_key] = self._merge(existing, normalized)
        return list(normalized_by_key.values())

    def extract_literature_key(self, record: RawRecord) -> str:
        if record.source_name != SourceName.PUBMED:
            raise ValueError("LiteratureNormalizer only accepts PubMed records.")
        xml_text = record.payload.get("xml")
        if isinstance(xml_text, str) and xml_text.strip():
            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError:
                root = None
            medline = root.find("./MedlineCitation") if root is not None else None
            pmid = clean_text(self._find_text(medline, "./PMID"))
            if pmid:
                return pmid
        return clean_text(record.source_id) or record.record_id

    def normalize(self, record: RawRecord) -> NormalizedLiteratureRecord:
        if record.source_name != SourceName.PUBMED:
            raise ValueError("LiteratureNormalizer only accepts PubMed records.")

        xml_text = record.payload.get("xml")
        if not isinstance(xml_text, str) or not xml_text.strip():
            raise ValueError("PubMed raw payload must contain XML text.")

        root = ET.fromstring(xml_text)
        medline = root.find("./MedlineCitation")
        article = root.find("./MedlineCitation/Article")
        pubmed_data = root.find("./PubmedData")

        pmid = clean_text(self._find_text(medline, "./PMID")) or self.extract_literature_key(record)
        doi = self._extract_doi(article, pubmed_data)
        abstract_sections = self._extract_abstract_sections(article, "./Abstract/AbstractText")
        other_abstracts = self._extract_abstract_sections(article, "./OtherAbstract/AbstractText")
        authors = self._extract_authors(article)
        affiliations = unique_strings(
            affiliation
            for author in authors
            for affiliation in author.affiliations
        )
        databanks = self._extract_databanks(article)
        linked_nct_ids = extract_nct_ids(
            [
                *[accession for databank in databanks for accession in databank.accession_numbers],
                *[section.text for section in abstract_sections],
                clean_text(self._find_text(article, "./ArticleTitle")) or "",
            ]
        )

        normalized = NormalizedLiteratureRecord(
            literature_key=pmid or record.record_id,
            pmid=pmid,
            doi=doi,
            source_traces=[self.build_source_trace(record)],
            title=clean_text(self._find_text(article, "./ArticleTitle")),
            journal=clean_text(self._find_text(article, "./Journal/Title")),
            publication_date=self._extract_publication_date(article),
            publication_types=unique_strings(
                self._iter_texts(article, "./PublicationTypeList/PublicationType")
            ),
            abstract_sections=abstract_sections,
            other_abstracts=other_abstracts,
            keywords=unique_strings(self._iter_texts(medline, "./KeywordList/Keyword")),
            mesh_terms=unique_strings(
                self._iter_texts(medline, "./MeshHeadingList/MeshHeading/DescriptorName")
            ),
            authors=authors,
            affiliations=affiliations,
            grants=self._extract_grants(article),
            databanks=databanks,
            linked_nct_ids=linked_nct_ids,
            related_pmids=self._extract_related_pmids(medline, pubmed_data),
            comments_corrections=self._extract_comments_corrections(medline, pubmed_data),
            quality_flags=self._build_quality_flags(abstract_sections, authors, doi),
        )
        return normalized

    def _merge(
        self,
        base: NormalizedLiteratureRecord,
        incoming: NormalizedLiteratureRecord,
    ) -> NormalizedLiteratureRecord:
        merged = base.model_copy(deep=True)
        merged.source_traces = [*base.source_traces, *incoming.source_traces]
        merged.publication_types = unique_strings(
            [*base.publication_types, *incoming.publication_types]
        )
        merged.keywords = unique_strings([*base.keywords, *incoming.keywords])
        merged.mesh_terms = unique_strings([*base.mesh_terms, *incoming.mesh_terms])
        merged.affiliations = unique_strings([*base.affiliations, *incoming.affiliations])
        merged.linked_nct_ids = unique_strings([*base.linked_nct_ids, *incoming.linked_nct_ids])
        merged.related_pmids = unique_strings([*base.related_pmids, *incoming.related_pmids])
        merged.comments_corrections = unique_strings(
            [*base.comments_corrections, *incoming.comments_corrections]
        )
        merged.quality_flags = unique_strings([*base.quality_flags, *incoming.quality_flags])
        merged.abstract_sections = self._merge_sections(base.abstract_sections, incoming.abstract_sections)
        merged.other_abstracts = self._merge_sections(base.other_abstracts, incoming.other_abstracts)
        merged.authors = self._merge_authors(base.authors, incoming.authors)
        merged.grants = self._merge_dataclasses(base.grants, incoming.grants, key_fields=("grant_id", "agency"))
        merged.databanks = self._merge_dataclasses(
            base.databanks,
            incoming.databanks,
            key_fields=("name",),
        )

        for field_name in ("pmid", "doi", "title", "journal", "publication_date"):
            if getattr(merged, field_name) is None:
                setattr(merged, field_name, getattr(incoming, field_name))
        return merged

    def build_source_trace(self, record: RawRecord) -> SourceTrace:
        return SourceTrace(
            raw_record_id=record.record_id,
            fetch_run_id=record.fetch_run_id,
            source_name=record.source_name,
            source_id=record.source_id,
            source_url=record.source_url,
            retrieved_at=record.retrieved_at,
        )

    def _extract_doi(self, article: ET.Element | None, pubmed_data: ET.Element | None) -> str | None:
        if article is not None:
            for node in article.findall("./ELocationID"):
                if clean_text(node.attrib.get("EIdType")) == "doi":
                    return clean_text("".join(node.itertext()))
        if pubmed_data is not None:
            for node in pubmed_data.findall("./ArticleIdList/ArticleId"):
                if clean_text(node.attrib.get("IdType")) == "doi":
                    return clean_text("".join(node.itertext()))
        return None

    def _extract_publication_date(self, article: ET.Element | None):
        if article is None:
            return None
        pub_date = article.find("./Journal/JournalIssue/PubDate")
        if pub_date is None:
            return None
        return build_structured_date(
            year=self._find_text(pub_date, "./Year"),
            month=self._find_text(pub_date, "./Month"),
            day=self._find_text(pub_date, "./Day"),
            raw_text=self._find_text(pub_date, "./MedlineDate"),
        )

    def _extract_abstract_sections(
        self,
        article: ET.Element | None,
        path: str,
    ) -> list[AbstractSection]:
        if article is None:
            return []
        sections: list[AbstractSection] = []
        for node in article.findall(path):
            text = clean_text("".join(node.itertext()))
            if text is None:
                continue
            sections.append(
                AbstractSection(
                    label=clean_text(node.attrib.get("Label")),
                    text=text,
                )
            )
        return sections

    def _extract_authors(self, article: ET.Element | None) -> list[AuthorRef]:
        if article is None:
            return []
        authors: list[AuthorRef] = []
        for node in article.findall("./AuthorList/Author"):
            affiliations = unique_strings(
                clean_text("".join(affiliation.itertext()))
                for affiliation in node.findall("./AffiliationInfo/Affiliation")
            )
            authors.append(
                AuthorRef(
                    collective_name=clean_text(self._find_text(node, "./CollectiveName")),
                    last_name=clean_text(self._find_text(node, "./LastName")),
                    fore_name=clean_text(self._find_text(node, "./ForeName")),
                    initials=clean_text(self._find_text(node, "./Initials")),
                    affiliations=affiliations,
                )
            )
        return authors

    def _extract_grants(self, article: ET.Element | None) -> list[GrantRef]:
        if article is None:
            return []
        grants: list[GrantRef] = []
        for node in article.findall("./GrantList/Grant"):
            grants.append(
                GrantRef(
                    grant_id=clean_text(self._find_text(node, "./GrantID")),
                    acronym=clean_text(self._find_text(node, "./Acronym")),
                    agency=clean_text(self._find_text(node, "./Agency")),
                    country=clean_text(self._find_text(node, "./Country")),
                )
            )
        return grants

    def _extract_databanks(self, article: ET.Element | None) -> list[DatabankRef]:
        if article is None:
            return []
        databanks: list[DatabankRef] = []
        for node in article.findall("./DataBankList/DataBank"):
            name = clean_text(self._find_text(node, "./DataBankName"))
            if name is None:
                continue
            databanks.append(
                DatabankRef(
                    name=name,
                    accession_numbers=unique_strings(
                        self._iter_texts(node, "./AccessionNumberList/AccessionNumber")
                    ),
                )
            )
        return databanks

    def _extract_related_pmids(
        self,
        medline: ET.Element | None,
        pubmed_data: ET.Element | None,
    ) -> list[str]:
        pmids: list[str] = []
        for node in self._comments_nodes(medline, pubmed_data):
            pmid = clean_text(self._find_text(node, "./PMID"))
            if pmid is not None:
                pmids.append(pmid)
        return unique_strings(pmids)

    def _extract_comments_corrections(
        self,
        medline: ET.Element | None,
        pubmed_data: ET.Element | None,
    ) -> list[str]:
        values: list[str] = []
        for node in self._comments_nodes(medline, pubmed_data):
            ref_type = clean_text(node.attrib.get("RefType"))
            ref_source = clean_text(self._find_text(node, "./RefSource"))
            pmid = clean_text(self._find_text(node, "./PMID"))
            parts = [part for part in (ref_type, ref_source, pmid) if part]
            if parts:
                values.append(" | ".join(parts))
        return unique_strings(values)

    def _comments_nodes(
        self,
        medline: ET.Element | None,
        pubmed_data: ET.Element | None,
    ) -> list[ET.Element]:
        roots = [root for root in (medline, pubmed_data) if root is not None]
        nodes: list[ET.Element] = []
        for root in roots:
            nodes.extend(root.findall("./CommentsCorrectionsList/CommentsCorrections"))
        return nodes

    def _build_quality_flags(
        self,
        abstract_sections: list[AbstractSection],
        authors: list[AuthorRef],
        doi: str | None,
    ) -> list[str]:
        flags: list[str] = []
        if not abstract_sections:
            flags.append("missing_abstract")
        if not authors:
            flags.append("missing_authors")
        if doi is None:
            flags.append("missing_doi")
        return flags

    def _find_text(self, root: ET.Element | None, path: str) -> str | None:
        if root is None:
            return None
        node = root.find(path)
        if node is None:
            return None
        return "".join(node.itertext())

    def _iter_texts(self, root: ET.Element | None, path: str) -> list[str]:
        if root is None:
            return []
        return [
            "".join(node.itertext())
            for node in root.findall(path)
            if clean_text("".join(node.itertext())) is not None
        ]

    def _merge_sections(
        self,
        base: list[AbstractSection],
        incoming: list[AbstractSection],
    ) -> list[AbstractSection]:
        merged: dict[tuple[str | None, str], AbstractSection] = {}
        for item in [*base, *incoming]:
            merged[(item.label, item.text)] = item
        return list(merged.values())

    def _merge_authors(self, base: list[AuthorRef], incoming: list[AuthorRef]) -> list[AuthorRef]:
        merged: dict[str, AuthorRef] = {}
        for item in [*base, *incoming]:
            key = "|".join(
                value or ""
                for value in (item.collective_name, item.last_name, item.fore_name, item.initials)
            )
            if key in merged:
                merged[key].affiliations = unique_strings(
                    [*merged[key].affiliations, *item.affiliations]
                )
                continue
            merged[key] = item
        return list(merged.values())

    def _merge_dataclasses(
        self,
        base: list[Any],
        incoming: list[Any],
        *,
        key_fields: tuple[str, ...],
    ) -> list[Any]:
        merged: dict[tuple[Any, ...], Any] = {}
        for item in [*base, *incoming]:
            key = tuple(getattr(item, field_name) for field_name in key_fields)
            existing = merged.get(key)
            if existing is not None and hasattr(existing, "accession_numbers"):
                existing.accession_numbers = unique_strings(
                    [*existing.accession_numbers, *item.accession_numbers]
                )
                continue
            merged[key] = item
        return list(merged.values())
