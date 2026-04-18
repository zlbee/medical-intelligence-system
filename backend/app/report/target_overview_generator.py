from app.report.base_generator import BaseReportSectionGenerator


class TargetOverviewReportGenerator(BaseReportSectionGenerator):
    section_title = "靶点概述"
    prompt_version = "target_overview_report_v1"
    task_name = "target_overview_report_generation"
    instruction_block = (
        "请生成“靶点概述”章节。"
        "重点说明靶点的疾病语境、研究主题、机制线索和当前证据覆盖情况。"
        "优先整合代表性文献与高价值主题词，不要把阶段/竞争态势写成主体。"
    )
