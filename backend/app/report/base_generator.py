from __future__ import annotations

import json
from typing import Any

from app.domain import GeneratedSectionDraft, SectionGenerationContext
from app.llm import LLMClient, LLMMessage, LLMMessageRole, LLMRequestOptions


class BaseReportSectionGenerator:
    """Shared structured-generation workflow for all stage-3 report sections."""

    section_title: str
    prompt_version: str
    task_name: str
    instruction_block: str

    def __init__(self, llm_client: LLMClient, *, model: str | None = None) -> None:
        self.llm_client = llm_client
        self.model = model

    def generate(self, context: SectionGenerationContext) -> GeneratedSectionDraft:
        draft = self.llm_client.generate_structured(
            task_name=self.task_name,
            messages=self._build_messages(context),
            response_model=GeneratedSectionDraft,
            model=self.model,
            options=LLMRequestOptions(temperature=0.2),
        )
        if not draft.title.strip():
            draft.title = self.section_title
        return draft

    def _build_messages(self, context: SectionGenerationContext) -> list[LLMMessage]:
        payload = {
            "query": {
                "target": context.query.target,
                "indication": context.query.indication,
                "aliases": context.query.aliases,
            },
            "section": {
                "name": context.section_name.value,
                "title": context.title,
                "facts": context.facts,
                "global_stats": context.global_stats,
                "selection_notes": context.selection_notes,
                "truncation_notes": context.truncation_notes,
                "warnings": context.warnings,
                "coverage_notes": context.coverage_notes,
            },
            "trial_evidence": [self._serialize_trial(item, context) for item in context.trials],
            "literature_evidence": [
                self._serialize_literature(item, context) for item in context.literature
            ],
            "trial_enrichments": [
                self._serialize_trial_enrichment(item, context)
                for item in context.trial_enrichments
            ],
            "literature_enrichments": [
                self._serialize_literature_enrichment(item, context)
                for item in context.literature_enrichments
            ],
        }
        return [
            LLMMessage(
                role=LLMMessageRole.SYSTEM,
                content=(
                    "你是一名严谨的医药情报分析助手。"
                    "你要为单个报告章节生成结构化 JSON。"
                    "只能使用提供的上下文，不允许补充外部事实。"
                    "正文默认使用中文，但保留英文实体名、试验号、期刊名、药物名和来源 URL。"
                    "trial_keys 与 literature_keys 只能引用上下文中已经出现的 key。"
                    "不要生成整篇报告，只生成当前章节。"
                ),
            ),
            LLMMessage(
                role=LLMMessageRole.USER,
                content=(
                    f"{self.instruction_block}\n\n"
                    "返回结构化 JSON，仅包含：title、summary、markdown_body、"
                    "key_takeaways、trial_keys、literature_keys、warnings。"
                    "markdown_body 不要再写一级标题。"
                    "如果证据不足，明确说明不足点，不要编造结论。\n\n"
                    f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
                ),
            ),
        ]

    def _serialize_trial(self, trial, context: SectionGenerationContext) -> dict[str, Any]:
        return {
            "trial_key": trial.trial_key,
            "nct_id": trial.nct_id,
            "title": trial.brief_title or trial.official_title or trial.nct_id or trial.trial_key,
            "summary": _truncate_text(trial.summary, 1000),
            "phase": trial.phase,
            "overall_status": trial.overall_status,
            "lead_sponsor": trial.lead_sponsor,
            "collaborators": trial.collaborators,
            "conditions": trial.conditions,
            "interventions": [item.name for item in trial.interventions],
            "countries": trial.countries,
            "has_results": trial.has_results,
            "primary_outcomes": trial.primary_outcomes[:5],
            "secondary_outcomes": trial.secondary_outcomes[:5],
            "source_url": _first_source_url(trial.source_traces),
        }

    def _serialize_literature(
        self,
        literature,
        context: SectionGenerationContext,
    ) -> dict[str, Any]:
        abstract_text = " ".join(section.text for section in literature.abstract_sections)
        return {
            "literature_key": literature.literature_key,
            "pmid": literature.pmid,
            "doi": literature.doi,
            "title": literature.title,
            "journal": literature.journal,
            "publication_date": (
                literature.publication_date.value.isoformat()
                if literature.publication_date and literature.publication_date.value
                else None
            ),
            "publication_types": literature.publication_types,
            "mesh_terms": literature.mesh_terms[:12],
            "keywords": literature.keywords[:12],
            "linked_nct_ids": literature.linked_nct_ids[:10],
            "abstract": _truncate_text(abstract_text, 1500),
            "source_url": _first_source_url(literature.source_traces),
        }

    def _serialize_trial_enrichment(
        self,
        enrichment,
        context: SectionGenerationContext,
    ) -> dict[str, Any]:
        insight = getattr(enrichment.dimension_insights, context.section_name.value)
        return {
            "trial_key": enrichment.trial_key,
            "nct_id": enrichment.nct_id,
            "final_score": getattr(enrichment.final_scores, context.section_name.value),
            "overall_score": enrichment.final_scores.overall_score,
            "summary": insight.summary,
            "key_points": insight.key_points,
            "evidence_snippets": [
                {
                    "field_name": snippet.field_name,
                    "excerpt": snippet.excerpt,
                    "reason": snippet.reason,
                }
                for snippet in insight.evidence_snippets
            ],
            "risk_signals": enrichment.risk_signals,
            "opportunity_signals": enrichment.opportunity_signals,
        }

    def _serialize_literature_enrichment(
        self,
        enrichment,
        context: SectionGenerationContext,
    ) -> dict[str, Any]:
        insight = getattr(enrichment.dimension_insights, context.section_name.value)
        return {
            "literature_key": enrichment.literature_key,
            "pmid": enrichment.pmid,
            "doi": enrichment.doi,
            "final_score": getattr(enrichment.final_scores, context.section_name.value),
            "overall_score": enrichment.final_scores.overall_score,
            "summary": insight.summary,
            "key_points": insight.key_points,
            "evidence_snippets": [
                {
                    "field_name": snippet.field_name,
                    "excerpt": snippet.excerpt,
                    "reason": snippet.reason,
                }
                for snippet in insight.evidence_snippets
            ],
            "study_design": enrichment.study_design,
            "mechanism_themes": enrichment.mechanism_themes,
            "efficacy_signals": enrichment.efficacy_signals,
            "safety_signals": enrichment.safety_signals,
            "trial_link_hints": enrichment.trial_link_hints,
        }


def _first_source_url(source_traces) -> str | None:
    for trace in source_traces:
        if trace.source_url:
            return trace.source_url
    return None


def _truncate_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]
