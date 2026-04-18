from __future__ import annotations

import pytest

from app.domain import AnalysisDimensionName, SECTION_TITLES, SectionGenerationContext
from app.report import (
    CompetitionAssessmentReportGenerator,
    PipelineOverviewReportGenerator,
    ResearchUpdateReportGenerator,
    TargetOverviewReportGenerator,
)
from tests.report_testkit import build_sample_analysis_bundle


@pytest.mark.parametrize(
    ("generator_cls", "section_name", "expected_trial_keys", "expected_literature_keys"),
    [
        (
            TargetOverviewReportGenerator,
            AnalysisDimensionName.TARGET_OVERVIEW,
            ["NCT03188393", "", "NCT03188393"],
            ["12345678", "missing", ""],
        ),
        (
            PipelineOverviewReportGenerator,
            AnalysisDimensionName.PIPELINE_OVERVIEW,
            ["NCT03188393"],
            [],
        ),
        (
            ResearchUpdateReportGenerator,
            AnalysisDimensionName.RESEARCH_UPDATE,
            [],
            ["12345678"],
        ),
        (
            CompetitionAssessmentReportGenerator,
            AnalysisDimensionName.COMPETITION_ASSESSMENT,
            ["NCT03188393"],
            ["12345678"],
        ),
    ],
)
def test_section_generators_return_structured_drafts(
    generator_cls,
    section_name,
    expected_trial_keys,
    expected_literature_keys,
) -> None:
    bundle = build_sample_analysis_bundle("fetch-run-1")
    section_input = getattr(bundle.section_inputs, section_name.value)
    context = SectionGenerationContext(
        fetch_run_id="fetch-run-1",
        analysis_bundle_id=bundle.bundle_id,
        section_name=section_name,
        title=SECTION_TITLES[section_name],
        query=bundle.query,
        facts=section_input.facts.model_dump(mode="json"),
        global_stats={"total_trial_count": bundle.global_stats.total_trial_count},
        trials=bundle.trials,
        literature=bundle.literature,
        trial_enrichments=bundle.trial_llm_enrichments,
        literature_enrichments=bundle.literature_llm_enrichments,
    )
    generator = generator_cls(
        StubLLMClient(
            {
                "title": "测试章节",
                "summary": "章节摘要",
                "markdown_body": "章节正文",
                "key_takeaways": ["要点 1", "要点 1", "  "],
                "trial_keys": expected_trial_keys,
                "literature_keys": expected_literature_keys,
                "warnings": [],
            }
        ),
        model="test-model",
    )

    draft = generator.generate(context)

    assert draft.title == "测试章节"
    assert draft.summary == "章节摘要"
    assert draft.markdown_body == "章节正文"
    assert draft.key_takeaways == ["要点 1"]
    assert "" not in draft.trial_keys
    assert "" not in draft.literature_keys


class StubLLMClient:
    def __init__(self, response: dict) -> None:
        self.response = response

    def generate_structured(self, **kwargs):
        return kwargs["response_model"].model_validate(self.response)
