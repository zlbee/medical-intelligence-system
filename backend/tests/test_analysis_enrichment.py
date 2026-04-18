from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.analyze.llm_enrichment import (
    LiteratureLLMStructuredOutput,
    TrialLLMStructuredOutput,
)


def test_trial_llm_structured_output_enforces_required_shape_and_limits() -> None:
    output = TrialLLMStructuredOutput.model_validate(
        {
            "dimension_insights": {
                "target_overview": {
                    "can_contribute": True,
                    "relevance_score": 88,
                    "confidence": 76,
                    "summary": "Relevant to target context.",
                    "key_points": ["Mentions HER2."],
                    "evidence_snippets": [
                        {
                            "field_name": "brief_title",
                            "excerpt": "A" * 400,
                            "reason": "Title mentions target.",
                        },
                        {
                            "field_name": "summary",
                            "excerpt": "Summary",
                            "reason": "Summary mentions indication.",
                        },
                        {
                            "field_name": "conditions",
                            "excerpt": "Breast cancer",
                            "reason": "Condition overlap.",
                        },
                    ],
                },
                "pipeline_overview": {
                    "can_contribute": True,
                    "relevance_score": 75,
                    "confidence": 81,
                    "summary": "Mid-stage pipeline evidence.",
                    "key_points": [],
                    "evidence_snippets": [],
                },
                "research_update": {
                    "can_contribute": False,
                    "relevance_score": 20,
                    "confidence": 65,
                    "summary": "Limited recency value.",
                    "key_points": [],
                    "evidence_snippets": [],
                },
                "competition_assessment": {
                    "can_contribute": True,
                    "relevance_score": 69,
                    "confidence": 73,
                    "summary": "Sponsor and phase help competition readout.",
                    "key_points": [],
                    "evidence_snippets": [],
                },
            },
            "llm_scores": {
                "target_overview": 90,
                "pipeline_overview": 80,
                "research_update": 30,
                "competition_assessment": 70,
                "overall_score": 72,
            },
        }
    )

    assert len(output.dimension_insights.target_overview.evidence_snippets) == 2
    assert len(output.dimension_insights.target_overview.evidence_snippets[0].excerpt) == 280


def test_literature_llm_structured_output_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        LiteratureLLMStructuredOutput.model_validate(
            {
                "dimension_insights": "not-an-object",
                "llm_scores": {
                    "target_overview": 80,
                    "pipeline_overview": 20,
                    "research_update": 95,
                    "competition_assessment": 30,
                    "overall_score": 65,
                },
            }
        )
