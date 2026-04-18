from app.report.base_generator import BaseReportSectionGenerator


class PipelineOverviewReportGenerator(BaseReportSectionGenerator):
    section_title = "在研管线概览"
    prompt_version = "pipeline_overview_report_v1"
    task_name = "pipeline_overview_report_generation"
    instruction_block = (
        "请生成“在研管线概览”章节。"
        "重点总结活跃试验数量、阶段分布、主要 sponsor、主要干预与适应症方向。"
        "结论必须围绕当前 fetch_run 中已选中的 trial 证据，避免泛泛而谈。"
    )
