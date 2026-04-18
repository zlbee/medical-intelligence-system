# 阶段 3 报告生成与 API 闭环方案

## 1. 目标

阶段 3 的目标，是在不重新抓取、不重跑阶段 2 分析的前提下，只基于数据库中已经持久化的阶段 2 结果，为单个 `fetch_run_id` 生成一份完整报告，并通过后端 API 暴露报告正文与来源清单。

本阶段的硬约束如下：

- 报告生成只消费 `analysis_snapshots`、`trial_llm_enrichments`、`literature_llm_enrichments`
- 报告作用域固定为单个 `fetch_run_id`
- 每个 `fetch_run_id` 只保留一个最新报告
- 阶段 3 不自动补跑 fetch 或 analysis

## 2. 输入与输出

### 2.1 输入

- `analysis_snapshots`
  - 提供 `AnalysisReadyBundle`
  - 其中包含四章节 `section_inputs`、`global_stats`、coverage 和阶段 2 warning
- `trial_llm_enrichments`
  - 提供记录级 trial 维度分析、评分和信号
- `literature_llm_enrichments`
  - 提供记录级 literature 维度分析、评分和信号

### 2.2 输出

- `ReportDocument`
  - 持久化后的最终报告对象
- `ReportSourceRef`
  - 报告实际引用的来源索引
- Markdown 镜像文件
  - 写入 `report_output_dir/{fetch_run_id}.md`
  - 作为调试与演示产物，不作为权威读取路径

## 3. 领域对象

阶段 3 新增的正式领域对象如下：

- `GeneratedSectionDraft`
  - 单章节的结构化 LLM 输出
  - 字段：`title`、`summary`、`markdown_body`、`key_takeaways`、`trial_keys`、`literature_keys`、`warnings`
- `SectionGenerationContext`
  - 单章节的最小输入证据包
  - 字段：`facts`、`global_stats`、`selection_notes`、`truncation_notes`、`coverage_notes`、已选中的 trial/literature 记录、对应 enrichments
- `ReportSection`
  - 最终报告中的一个章节
  - 字段：`section_name`、`title`、`summary`、`markdown_body`、`key_takeaways`、`trial_keys`、`literature_keys`、`warnings`
- `ReportSourceRef`
  - 最终报告中真实落地的一条来源引用
  - 字段：`report_id`、`fetch_run_id`、`section_name`、`source_type`、`record_key`、`source_id`、`display_title`、`source_url`、`display_order`
- `ReportWarningSummary`
  - 对报告 warning 的聚合摘要
- `ReportDocument`
  - 最终持久化对象
  - 字段：`report_id`、`fetch_run_id`、`analysis_bundle_id`、`target`、`indication`、`markdown_content`、`sections`、`warnings`、`warning_summary`、`source_refs`、`model`、`prompt_versions`、`generated_at`

## 4. 生成链路

### 4.1 上下文构建

`ReportContextBuilder` 负责完成以下工作：

1. 读取当前 `fetch_run_id` 对应的 `AnalysisReadyBundle`
2. 读取同一个 `fetch_run_id` 对应的 trial/literature enrichments
3. 按 `section_inputs.<section>.trial_keys/literature_keys` 做 join
4. 为四个章节分别构造 `SectionGenerationContext`

它的行为约束如下：

- 如果 `analysis_snapshot` 不存在，直接抛出 `409 analysis_snapshot_required`
- 如果某个已选 key 在 snapshot 中丢失，记录 warning，但不中断整篇报告
- 如果某个已选 key 没有 enrichment，仍保留 deterministic 记录进入上下文，同时记录 warning

### 4.2 章节生成

章节生成器共四个：

- `TargetOverviewReportGenerator`
- `PipelineOverviewReportGenerator`
- `ResearchUpdateReportGenerator`
- `CompetitionAssessmentReportGenerator`

共性约束：

- 全部通过 `LLMClient.generate_structured()` 输出 `GeneratedSectionDraft`
- Prompt 默认使用中文
- 保留英文实体名、药物名、试验号、期刊名、来源 URL
- 只能引用当前章节上下文中已经提供的 `trial_keys` 与 `literature_keys`
- 不允许一次生成整篇报告，只允许生成单章节

### 4.3 引用校验

`ReportGenerationService` 在拿到 `GeneratedSectionDraft` 后，会进行一次引用子集校验：

- 如果 draft 里引用了超出当前章节上下文的 key，该 key 会被丢弃
- 同时写入 `report_section_reference_filtered` warning

因此，最终报告中的来源引用只来自实际保留下来的 key，而不是阶段 2 的全部候选 key。

### 4.4 Markdown 渲染

`MarkdownRenderer` 负责把四个 `ReportSection` 按固定顺序拼成系统权威 Markdown：

1. `target_overview`
2. `pipeline_overview`
3. `research_update`
4. `competition_assessment`

Markdown 顶部还会包含：

- `fetch_run_id`
- `analysis_bundle_id`
- 生成时间
- 模型名
- prompt versions
- warning summary

## 5. 容错策略

### 5.1 单章节失败

如果某一章节的 LLM 调用失败，不中断整篇报告，而是回退成占位章节：

- `title` 仍使用固定章节标题
- `summary` 标明该章节生成失败
- `markdown_body` 使用 deterministic facts 自动拼出最小摘要
- `warnings` 中记录失败信息

### 5.2 全章节失败

如果四个章节全部失败，返回：

- HTTP `502`
- `report_generation_failed`

### 5.3 LLM 不可用

如果当前环境无法构建 `LLMClient`，`POST /api/fetches/{fetch_run_id}/report` 返回：

- HTTP `503`
- `report_llm_unavailable`

### 5.4 Markdown 镜像失败

如果 Markdown 文件镜像写入失败：

- API 仍然成功返回
- 只在报告 warning 中记录 `report_markdown_mirror_failed`

## 6. 持久化

### 6.1 `reports`

字段语义：

- `id`
- `fetch_run_id`
- `analysis_bundle_id`
- `target`
- `payload`
- `generated_at`
- `updated_at`

约束：

- `fetch_run_id` 唯一
- 同一个 `fetch_run_id` 每次重建报告时覆盖旧报告

### 6.2 `report_source_refs`

字段语义：

- `report_id`
- `fetch_run_id`
- `section_name`
- `source_type`
- `record_key`
- `source_id`
- `display_title`
- `source_url`
- `display_order`
- `payload`

约束：

- 每次重建报告时，当前 `fetch_run_id` 的旧来源引用会被全量替换
- 查询时按固定章节顺序和 `display_order` 返回

## 7. API 约定

阶段 3 对外暴露三个接口：

### 7.1 `POST /api/fetches/{fetch_run_id}/report`

作用：

- 同步生成并持久化当前 `fetch_run_id` 的最新报告

成功返回：

- `ReportResponse`

错误返回：

- `404 fetch_run_not_found`
- `409 analysis_snapshot_required`
- `503 report_llm_unavailable`
- `502 report_generation_failed`

### 7.2 `GET /api/fetches/{fetch_run_id}/report`

作用：

- 读取当前 `fetch_run_id` 的最新报告

成功返回：

- `ReportResponse`

错误返回：

- `404 report_not_found`

### 7.3 `GET /api/fetches/{fetch_run_id}/report/sources`

作用：

- 读取当前 `fetch_run_id` 的最新报告来源清单

成功返回：

- `ReportSourceRefListResponse`

返回特点：

- 扁平 `items`
- 按固定章节顺序和 `display_order` 排序

## 8. 测试范围

本阶段至少覆盖以下测试：

- 章节生成器结构化输出测试
- `ReportContextBuilder` 上下文 join 测试
- `MarkdownRenderer` 顺序与 warning 渲染测试
- `ReportRepository` / `ReportSourceRefRepository` 替换写入测试
- `ReportGenerationService` 成功、单章失败、全章失败、缺少 snapshot 测试
- `POST /report`、`GET /report`、`GET /report/sources` API 测试
- `fetch -> analysis -> report -> sources` smoke test

## 9. 当前边界

本轮阶段 3 明确不做以下事情：

- 不新增前端报告页面
- 不支持报告多版本历史
- 不在阶段 3 内自动触发 fetch 或 analysis
- 不支持英文版或双语版报告
- 不支持异步任务队列与后台重试

本文件是阶段 3 报告生成与 API 闭环的权威说明；如果实现细节与旧计划文档存在冲突，以本文件为准。
