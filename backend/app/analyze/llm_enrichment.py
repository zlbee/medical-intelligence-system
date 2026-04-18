from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.analyze.scoring import blend_literature_scores, blend_trial_scores
from app.domain import (
    DimensionInsightBreakdown,
    LLMScoreBreakdown,
    LiteratureLLMEnrichment,
    NormalizedLiteratureRecord,
    NormalizedTrialRecord,
    RuleScoreBreakdown,
    TargetQuery,
    TrialLLMEnrichment,
)
from app.llm import LLMClient, LLMMessage, LLMMessageRole, LLMRequestOptions


class TrialLLMStructuredOutput(BaseModel):
    """Structured LLM enrichment for one normalized trial record."""

    dimension_insights: DimensionInsightBreakdown
    llm_scores: LLMScoreBreakdown
    modality: str | None = None
    asset_candidates: list[str] = Field(default_factory=list)
    company_candidates: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    opportunity_signals: list[str] = Field(default_factory=list)


class LiteratureLLMStructuredOutput(BaseModel):
    """Structured LLM enrichment for one normalized literature record."""

    dimension_insights: DimensionInsightBreakdown
    llm_scores: LLMScoreBreakdown
    study_design: str | None = None
    mechanism_themes: list[str] = Field(default_factory=list)
    efficacy_signals: list[str] = Field(default_factory=list)
    safety_signals: list[str] = Field(default_factory=list)
    trial_link_hints: list[str] = Field(default_factory=list)


class TrialLLMEnhancementService:
    """Runs structured LLM enrichment for a single normalized trial record."""

    PROMPT_VERSION = "trial_enrichment_v1"

    def __init__(self, llm_client: LLMClient, *, model: str | None = None) -> None:
        self.llm_client = llm_client
        self.model = model

    def enhance(
        self,
        *,
        fetch_run_id: str,
        query: TargetQuery,
        trial: NormalizedTrialRecord,
        rule_scores: RuleScoreBreakdown,
    ) -> TrialLLMEnrichment:
        response = self.llm_client.generate_structured(
            task_name="trial_llm_enrichment",
            messages=self._build_messages(query, trial),
            response_model=TrialLLMStructuredOutput,
            model=self.model,
            options=LLMRequestOptions(temperature=0.1),
        )
        return TrialLLMEnrichment(
            fetch_run_id=fetch_run_id,
            trial_key=trial.trial_key,
            nct_id=trial.nct_id,
            dimension_insights=response.dimension_insights,
            rule_scores=rule_scores,
            llm_scores=response.llm_scores,
            final_scores=blend_trial_scores(rule_scores, response.llm_scores),
            modality=response.modality,
            asset_candidates=response.asset_candidates,
            company_candidates=response.company_candidates,
            risk_signals=response.risk_signals,
            opportunity_signals=response.opportunity_signals,
            model=self.model,
            prompt_version=self.PROMPT_VERSION,
        )

    def _build_messages(
        self,
        query: TargetQuery,
        trial: NormalizedTrialRecord,
    ) -> list[LLMMessage]:
        payload = {
            "query": {
                "target": query.target,
                "indication": query.indication,
                "aliases": query.aliases,
            },
            "trial": _serialize_trial_record(trial),
        }
        return [
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content=(
                    "You are a biomedical analysis assistant. "
                    "Assess how one normalized clinical trial record can contribute to "
                    "target_overview, pipeline_overview, research_update, and "
                    "competition_assessment. Only use the provided normalized fields. "
                    "Do not infer facts from raw source systems or outside knowledge. "
                    "Evidence snippets must quote or paraphrase only the provided fields."
                ),
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content=(
                    "Return structured JSON only. "
                    "Score each dimension from 0 to 100, give a short summary, key points, "
                    "and up to two evidence snippets per dimension. "
                    "Also extract modality, likely asset candidates, company candidates, "
                    "risk signals, and opportunity signals.\n\n"
                    f"{json.dumps(payload, ensure_ascii=True, indent=2)}"
                ),
            ),
        ]


class LiteratureLLMEnhancementService:
    """Runs structured LLM enrichment for a single normalized literature record."""

    PROMPT_VERSION = "literature_enrichment_v1"

    def __init__(self, llm_client: LLMClient, *, model: str | None = None) -> None:
        self.llm_client = llm_client
        self.model = model

    def enhance(
        self,
        *,
        fetch_run_id: str,
        query: TargetQuery,
        literature: NormalizedLiteratureRecord,
        rule_scores: RuleScoreBreakdown,
    ) -> LiteratureLLMEnrichment:
        response = self.llm_client.generate_structured(
            task_name="literature_llm_enrichment",
            messages=self._build_messages(query, literature),
            response_model=LiteratureLLMStructuredOutput,
            model=self.model,
            options=LLMRequestOptions(temperature=0.1),
        )
        return LiteratureLLMEnrichment(
            fetch_run_id=fetch_run_id,
            literature_key=literature.literature_key,
            pmid=literature.pmid,
            doi=literature.doi,
            dimension_insights=response.dimension_insights,
            rule_scores=rule_scores,
            llm_scores=response.llm_scores,
            final_scores=blend_literature_scores(rule_scores, response.llm_scores),
            study_design=response.study_design,
            mechanism_themes=response.mechanism_themes,
            efficacy_signals=response.efficacy_signals,
            safety_signals=response.safety_signals,
            trial_link_hints=response.trial_link_hints,
            model=self.model,
            prompt_version=self.PROMPT_VERSION,
        )

    def _build_messages(
        self,
        query: TargetQuery,
        literature: NormalizedLiteratureRecord,
    ) -> list[LLMMessage]:
        payload = {
            "query": {
                "target": query.target,
                "indication": query.indication,
                "aliases": query.aliases,
            },
            "literature": _serialize_literature_record(literature),
        }
        return [
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content=(
                    "You are a biomedical literature analysis assistant. "
                    "Assess how one normalized literature record can contribute to "
                    "target_overview, pipeline_overview, research_update, and "
                    "competition_assessment. Only use the provided normalized fields. "
                    "Do not add outside biomedical facts. Evidence snippets must come from "
                    "the provided title, abstract, keywords, MeSH terms, or other normalized fields."
                ),
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content=(
                    "Return structured JSON only. "
                    "Score each dimension from 0 to 100, give a short summary, key points, "
                    "and up to two evidence snippets per dimension. "
                    "Also extract study design, mechanism themes, efficacy signals, "
                    "safety signals, and trial link hints.\n\n"
                    f"{json.dumps(payload, ensure_ascii=True, indent=2)}"
                ),
            ),
        ]


def _serialize_trial_record(trial: NormalizedTrialRecord) -> dict[str, object]:
    return {
        "trial_key": trial.trial_key,
        "nct_id": trial.nct_id,
        "brief_title": trial.brief_title,
        "official_title": trial.official_title,
        "acronym": trial.acronym,
        "summary": trial.summary,
        "study_type": trial.study_type,
        "phase": trial.phase,
        "overall_status": trial.overall_status,
        "last_known_status": trial.last_known_status,
        "lead_sponsor": trial.lead_sponsor,
        "collaborators": trial.collaborators,
        "conditions": trial.conditions,
        "keywords": trial.keywords,
        "browse_terms": trial.browse_terms,
        "interventions": [
            {
                "name": item.name,
                "intervention_type": item.intervention_type,
                "other_names": item.other_names,
            }
            for item in trial.interventions
        ],
        "arm_groups": [
            {
                "label": item.label,
                "arm_type": item.arm_type,
                "description": item.description,
                "intervention_names": item.intervention_names,
            }
            for item in trial.arm_groups
        ],
        "timeline": {
            "start_date": _serialize_normalized_date(trial.start_date),
            "primary_completion_date": _serialize_normalized_date(
                trial.primary_completion_date
            ),
            "completion_date": _serialize_normalized_date(trial.completion_date),
            "study_first_post_date": _serialize_normalized_date(trial.study_first_post_date),
            "last_update_post_date": _serialize_normalized_date(trial.last_update_post_date),
        },
        "enrollment": trial.enrollment,
        "countries": trial.countries,
        "location_count": trial.location_count,
        "has_results": trial.has_results,
        "primary_outcomes": trial.primary_outcomes,
        "secondary_outcomes": trial.secondary_outcomes,
        "quality_flags": trial.quality_flags,
    }


def _serialize_literature_record(
    literature: NormalizedLiteratureRecord,
) -> dict[str, object]:
    return {
        "literature_key": literature.literature_key,
        "pmid": literature.pmid,
        "doi": literature.doi,
        "title": literature.title,
        "journal": literature.journal,
        "publication_date": _serialize_normalized_date(literature.publication_date),
        "publication_types": literature.publication_types,
        "abstract_sections": [
            {"label": section.label, "text": section.text}
            for section in literature.abstract_sections
        ],
        "other_abstracts": [
            {"label": section.label, "text": section.text}
            for section in literature.other_abstracts
        ],
        "keywords": literature.keywords,
        "mesh_terms": literature.mesh_terms,
        "authors": [
            {
                "collective_name": author.collective_name,
                "last_name": author.last_name,
                "fore_name": author.fore_name,
                "initials": author.initials,
                "affiliations": author.affiliations,
            }
            for author in literature.authors
        ],
        "affiliations": literature.affiliations,
        "grants": [
            {
                "grant_id": grant.grant_id,
                "acronym": grant.acronym,
                "agency": grant.agency,
                "country": grant.country,
            }
            for grant in literature.grants
        ],
        "databanks": [
            {
                "name": databank.name,
                "accession_numbers": databank.accession_numbers,
            }
            for databank in literature.databanks
        ],
        "linked_nct_ids": literature.linked_nct_ids,
        "related_pmids": literature.related_pmids,
        "comments_corrections": literature.comments_corrections,
        "quality_flags": literature.quality_flags,
    }


def _serialize_normalized_date(value) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "raw_text": value.raw_text,
        "value": value.value.isoformat() if value.value is not None else None,
        "precision": value.precision.value if value.precision is not None else None,
    }
