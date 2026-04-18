# 阶段 3 报告生成与后端 API 闭环实施计划

## Summary

本轮阶段 3 以“只消费数据库中的阶段 2 结果”为硬约束来落地报告生成，不再重新抓取或重跑分析。报告生成链路只读取当前 `fetch_run_id` 对应的 `analysis_snapshots`、`trial_llm_enrichments`、`literature_llm_enrichments`，并产出一个“每个 `fetch_run_id` 仅保留最新版本”的 `ReportDocument`。API 采用 fetch-scoped 形式：`POST /api/fetches/{fetch_run_id}/report`、`GET /api/fetches/{fetch_run_id}/report`、`GET /api/fetches/{fetch_run_id}/report/sources`，缺少阶段 2 前置输入时直接报错，不在阶段 3 内自动补跑 analysis。

## Key Changes

- 在 `backend/app/domain` 新增阶段 3 正式对象：`ReportDocument`、`ReportSection`、`ReportSourceRef`、`ReportWarningSummary`、`SectionGenerationContext`、`GeneratedSectionDraft`。`ReportDocument` 至少包含 `report_id`、`fetch_run_id`、`analysis_bundle_id`、`target`、`indication`、`markdown_content`、`sections`、`warnings`、`source_refs`、`model`、`prompt_versions`、`generated_at`。
- `ReportSection` 固定对齐四个章节：`target_overview`、`pipeline_overview`、`research_update`、`competition_assessment`。每章保存 `title`、`summary`、`markdown_body`、`key_takeaways`、`trial_keys`、`literature_keys`、`warnings`。章节生成器输出结构化 section draft，再由 `markdown_renderer` 统一拼 Markdown，不直接让模型一次性生成整篇报告。
- 在 `backend/app/report` 实现四个章节生成器和 `markdown_renderer.py`。每个章节生成器只接收对应的 `SectionGenerationContext`，即：
  - `analysis_snapshot.section_inputs.<section>` 的 facts、selection/truncation notes、coverage 信息
  - 当前章节选中的 trial/literature 记录
  - 与当前章节维度匹配的 `trial_llm_enrichments` / `literature_llm_enrichments`
  - `global_stats` 中与该章节直接相关的统计结果
- 章节 prompt 一律通过现有 `LLMClient.generate_structured()` 输出强类型 `GeneratedSectionDraft`。Prompt 默认使用中文生成报告正文，但保留英文原始实体名、试验号、期刊名、药物名和来源 URL。生成器必须要求模型只引用当前上下文中的记录键，不允许发明新的 trial/literature key。
- 在 `backend/app/report` 新增 `ReportContextBuilder`。它负责从数据库取回 `AnalysisReadyBundle` 和两类 enrichment，按 `section_inputs` 选中的 key 做 join，生成四个章节的最小证据包。它只读取数据库中的阶段 2 结果，不读取 `raw_records`、不调用 analysis pipeline、也不从外部源拉数据。
- 在 `backend/app/repository` 新增 `ReportRepository` 与 `ReportSourceRefRepository`，并新增两张表：
  - `reports`：主键 `id`，唯一键 `fetch_run_id`，保存 `analysis_bundle_id`、`target`、`payload JSON`、`generated_at`、`updated_at`
  - `report_source_refs`：每条引用一行，字段至少包含 `report_id`、`fetch_run_id`、`section_name`、`source_type`、`record_key`、`source_id`、`display_title`、`source_url`、`display_order`、`payload JSON`
- 报告持久化语义固定为“每个 `fetch_run_id` 只保留一个最新报告”。`POST /api/fetches/{fetch_run_id}/report` 每次都会重新生成并覆盖当前 fetch 的最新报告，同时生成新的 `report_id`，旧 source refs 全量替换。
- 在 `backend/app/orchestration` 新增 `ReportGenerationService`。执行顺序固定为：
  1. 校验 `fetch_run_id` 存在
  2. 读取 `AnalysisReadyBundle`
  3. 读取 trial/literature enrichment
  4. 若 `analysis_snapshot` 不存在则返回 `409`
  5. 构建四个章节的 `SectionGenerationContext`
  6. 依次生成四个章节的 `GeneratedSectionDraft`
  7. 对 draft 中的 `trial_keys` / `literature_keys` 做子集校验，超出 `section_inputs` 的引用一律丢弃并写 warning
  8. 由 `markdown_renderer` 生成完整 Markdown
  9. 构造 `ReportDocument` 与 `ReportSourceRef`
  10. 持久化报告与来源引用
- Section-level LLM 失败策略固定为“尽量完成整篇报告”。单章失败时，不中断整篇报告，而是为该章节写入一个占位 section：
  - `title` 保持该章节标题
  - `summary` 说明该章节生成失败
  - `markdown_body` 退化为基于 deterministic facts 的最小摘要
  - 写入章节 warning
  - 继续生成剩余章节
  只有四章全部失败或 LLM 客户端不可用时，`POST` 才返回错误。
- 来源引用的来源固定是“最终章节实际引用的 key”，不是阶段 2 全部候选 key。`ReportSourceRef` 由 service 在 LLM 结果落地后，根据 section draft 中保留的 `trial_keys` / `literature_keys` 去 snapshot 中回填 `source_id`、`title/nct_id/pmid`、`source_url`、`section_name` 和排序号。
- API 仅做阶段 3 后端闭环，不改前端页面。新增 fetch-scoped 路由和 schema：
  - `POST /api/fetches/{fetch_run_id}/report`：同步生成/覆盖最新报告
  - `GET /api/fetches/{fetch_run_id}/report`：读取该 fetch 最新报告
  - `GET /api/fetches/{fetch_run_id}/report/sources`：读取该 fetch 最新报告的来源清单
  响应体至少返回 `report_id`、`fetch_run_id`、`target`、`markdown_content`、`sections`、`warnings`、`generated_at`；sources 接口返回扁平 `items` 列表，按 section 和 display_order 排序。
- 文档同步方式固定为：
  - 更新 `docs/实施阶段拆分与里程碑.md` 的阶段 3 任务与验收条件，使其改为 fetch-scoped 报告接口
  - 新增一份阶段 3 设计文档，建议命名为 `docs/阶段3报告生成与API闭环方案.md`，作为本轮报告领域对象、接口和失败策略的权威说明

## Test Plan

- 章节生成器单测：每个 section generator 在 stub LLM 下能生成合法 `GeneratedSectionDraft`；非法 key、空 key、越界引用会被过滤并生成 warning。
- `ReportContextBuilder` 单测：能从 `analysis_snapshot + trial/literature enrichments` 正确构建四个章节的最小证据包；当某些选中 key 找不到 enrichment 时，继续返回 context 并记录 warning。
- `markdown_renderer` 单测：四章节顺序固定、Markdown 标题层级固定、warning summary 能正确拼装；单章失败时占位 section 输出稳定。
- `ReportGenerationService` 集成测试：
  - analysis snapshot 和 enrichments 都存在时，能生成并持久化完整报告
  - 缺少 analysis snapshot 时返回 `409`
  - 某一章节 LLM 失败时，整篇报告仍成功生成并带 warning
  - 四章全部失败时返回错误
- repository 测试：
  - `reports` 按 `fetch_run_id` 覆盖写入
  - `report_source_refs` 在重建报告时会全量替换
  - `GET /sources` 返回的引用与最新 `report_id` 一致
- API 测试：
  - `POST /api/fetches/{fetch_run_id}/report` 返回完整 `ReportResponse`
  - `GET /api/fetches/{fetch_run_id}/report` 返回已持久化的最新报告
  - `GET /api/fetches/{fetch_run_id}/report/sources` 返回来源清单并可回溯到 section
  - 缺少 analysis snapshot 时接口返回约定错误码
- 全量后端 `pytest`，并补一个基于固定 fixture 的端到端 smoke test：`fetch -> analysis -> report -> sources` 整链路贯通。

## Assumptions

- 阶段 3 的报告生成只消费数据库中的阶段 2 结果，不自动触发 fetch 或 analysis；调用方必须先完成阶段 2。
- 报告持久化采用“每个 `fetch_run_id` 一个最新报告”的语义，不做多版本历史。
- 默认报告语言为中文，保留英文原始实体名和来源标识；如需英文版或双语版，放到后续迭代。
- `reports` 表中的 Markdown 正文是系统权威版本；同时将 `.md` 文件镜像写入 `report_output_dir` 作为演示和调试产物，镜像写入失败只记 warning，不影响 API 成功返回。
- 本轮阶段 3 只实现后端报告闭环与 API，不包含前端报告页面改造；前端接入留到阶段 4。

