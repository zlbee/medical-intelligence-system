from app.report.base_generator import BaseReportSectionGenerator


class CompetitionAssessmentReportGenerator(BaseReportSectionGenerator):
    section_title = "竞争格局判断"
    prompt_version = "competition_assessment_report_v1"
    task_name = "competition_assessment_report_generation"
    instruction_block = (
        "请生成“竞争格局判断”章节。"
        "重点分析 sponsor 集中度、后期项目密度、招募状态、结果披露情况，以及文献对竞争态势的支持或限制。"
        "结论应明确区分确定性事实、趋势判断和证据不足点。"
    )
