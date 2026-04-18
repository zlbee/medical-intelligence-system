from app.report.base_generator import BaseReportSectionGenerator


class ResearchUpdateReportGenerator(BaseReportSectionGenerator):
    section_title = "近期研究动态"
    prompt_version = "research_update_report_v1"
    task_name = "research_update_report_generation"
    instruction_block = (
        "请生成“近期研究动态”章节。"
        "重点概括最近文献动向、高价值研究、主要机制主题、研究设计与疗效/安全性线索。"
        "优先使用 recent 和 high-value 论文证据，不要把竞争格局分析写成主体。"
    )
