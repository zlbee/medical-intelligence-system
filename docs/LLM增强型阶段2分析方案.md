## LLM 增强型阶段 2 分析方案

### Summary

在现有阶段 2 链路上，把 LLM 增强作为 `AnalysisPipelineService` 内的自动子阶段执行，不新增独立触发 API。实现方式是：

- 默认对每条 `NormalizedTrialRecord` 和 `NormalizedLiteratureRecord` 做全量逐条 LLM 结构化增强
- 支持通过 `.env` 配置切换为“先按规则分预筛，再只增强头部 N 条”的节流模式
- 使用独立增强对象承载 LLM 结果，不直接污染 `Normalized*Record`
- 为每条记录同时保存四维度分数、整体总分、证据摘录和简短判断
- 在 `/app/analyze` 中保留 `rule score`、`LLM score`、`final blended score`
- LLM 失败时走最佳努力策略：记录 warning，保留现有规则分析结果，不阻断阶段 2

### Key Changes

#### 1. 新增独立的 LLM 增强领域对象

新增一组强类型对象，全部以“记录级增强”为中心，而不是直接往 `Normalized*Record` 塞字段。

核心对象：

- `AnalysisDimensionName`
固定四个值：`target_overview`、`pipeline_overview`、`research_update`、`competition_assessment`
- `EvidenceSnippet`
字段固定为：`field_name`、`excerpt`、`reason`
- `DimensionInsight`
字段固定为：`can_contribute`、`relevance_score`、`confidence`、`summary`、`key_points`、`evidence_snippets`
- `RuleScoreBreakdown`
四维度分数 + `overall_score`
- `LLMScoreBreakdown`
四维度分数 + `overall_score` + `confidence`
- `FinalScoreBreakdown`
四维度分数 + `overall_score`
- `TrialLLMEnrichment`
包含：`fetch_run_id`、`trial_key`、`nct_id`、`dimension_insights`、`rule_scores`、`llm_scores`、`final_scores`、`modality`、`asset_candidates`、`company_candidates`、`risk_signals`、`opportunity_signals`、`model`、`prompt_version`、`generated_at`
- `LiteratureLLMEnrichment`
包含：`fetch_run_id`、`literature_key`、`pmid`、`doi`、`dimension_insights`、`rule_scores`、`llm_scores`、`final_scores`、`study_design`、`mechanism_themes`、`efficacy_signals`、`safety_signals`、`trial_link_hints`、`model`、`prompt_version`、`generated_at`

结构要求：

- `dimension_insights` 固定是四个命名字段，不用 `dict[str, Any]`
- 每个维度最多保留 `2` 条 `evidence_snippets`
- 每条 `excerpt` 截断到 `280` 字以内
- `prompt_version` 固定从 `"trial_enrichment_v1"` / `"literature_enrichment_v1"` 起步

#### 2. 扩展 `AnalysisReadyBundle`

`AnalysisReadyBundle` 增加：

- `trial_llm_enrichments: list[TrialLLMEnrichment]`
- `literature_llm_enrichments: list[LiteratureLLMEnrichment]`
- `llm_enrichment_summary`
固定字段：`trial_total`、`trial_succeeded`、`literature_total`、`literature_succeeded`、`warning_count`、`model`、`prompt_versions`

不改 `NormalizedTrialRecord` 和 `NormalizedLiteratureRecord` 的核心语义，仍保持它们是“确定性标准化层”。

#### 3. 在阶段 2 编排内自动执行 LLM 增强

在 `AnalysisPipelineService.build()` 中固定顺序为：

1. 从原始记录生成 `NormalizedTrialRecord` / `NormalizedLiteratureRecord`
2. 持久化标准化记录
3. 生成 `rule score`
4. 根据配置决定 LLM 增强范围：
   - `MIS_ANALYSIS_LLM_ENRICHMENT_FULL_SCAN=true` 时，对全部标准化记录逐条增强
   - `MIS_ANALYSIS_LLM_ENRICHMENT_FULL_SCAN=false` 时，先按 `rule_scores.overall_score` 排序，再对 trial 和 literature 各自前 `MIS_ANALYSIS_LLM_ENRICHMENT_TOP_N` 条逐条增强
5. 运行记录级 LLM 结构化增强
6. 解析 LLM 返回的 `llm score`
7. 计算 `final blended score`
8. 用 `final blended score` 更新 selector 和章节输入，未增强记录自然回退到 `rule score`
9. 组装带 enrichment 的 `AnalysisReadyBundle`
10. 持久化分析快照

实现要求：

- LLM 服务统一通过现有 `build_llm_client()` 获取 `LLMClient`
- 全部使用 `generate_structured()`，不允许自由文本后解析
- Prompt 输入只使用 `Normalized*Record` 字段，不读取 raw payload 原文 JSON/XML
- LLM 调用按“单条记录一次请求”实现，不做多记录合并 Prompt
- 节流模式下的预筛排序只使用元数据规则分，不依赖任何已有 LLM 结果

#### 4. Prompt 与结构化输出约定

为 trial 和 literature 各自定义一份严格的 response model，不共用一个宽泛 schema。

Trial prompt 重点要求 LLM 输出：

- 该试验对四个维度是否有贡献
- 它最能支撑哪个维度
- 管线价值、竞争价值、潜在风险/机会
- 资产、公司、 modality 候选
- 证据摘录必须只来自输入字段，不允许编造

Literature prompt 重点要求 LLM 输出：

- 该文献对四个维度是否有贡献
- 机制主题、研究设计、疗效/安全性信号
- 是否可作为近期研究动态核心证据
- 是否能辅助竞争判断
- 证据摘录必须只来自标题、摘要、关键词、MeSH 等输入字段

所有 score 统一为 `0-100` 浮点区间。

#### 5. 评分体系重构

把当前 `/app/analyze/scoring.py` 改成“显式产出四维度规则分”的形式，而不是只给几个零散函数。

固定评分组织：

- `rule_scores`
- `llm_scores`
- `final_scores`

固定融合公式：

- `final_dimension_score = 0.65 * rule_dimension_score + 0.35 * llm_dimension_score`
- `final_overall_score` 使用类型特异权重

Trial 的整体权重固定为：

- `target_overview`: `0.15`
- `pipeline_overview`: `0.35`
- `research_update`: `0.10`
- `competition_assessment`: `0.40`

Literature 的整体权重固定为：

- `target_overview`: `0.30`
- `pipeline_overview`: `0.10`
- `research_update`: `0.40`
- `competition_assessment`: `0.20`

实现要求：

- 先把现有 rule score 归一到 `0-100`
- selector 后续统一按 `final_scores.<dimension>` 排序
- 章节 facts 构建时允许聚合 LLM 的 `key_points`、`mechanism_themes`、`risk_signals` 等，但不直接把长摘要塞进 facts

#### 6. 持久化与 API

新增两张 enrichment 表：

- `trial_llm_enrichments`
- `literature_llm_enrichments`

表结构策略与现有标准化记录一致：

- 主键 `id`
- 唯一键 `(fetch_run_id, trial_key)` 或 `(fetch_run_id, literature_key)`
- 保留检索字段 `nct_id` / `pmid` / `doi`
- 完整 enrichment 存 JSON `payload`

失败记录不写 enrichment 表，只在 `AnalysisReadyBundle.warnings` 和 `llm_enrichment_summary` 中体现。

API 变更：

- 不新增独立 enrichment API
- 继续复用现有 `/api/fetches/{fetch_run_id}/analysis`
- 该响应增加 `llm_enrichment_summary`
- 不把全量 enrichment 明细直接暴露给前端摘要接口，避免响应过大
- 如需调试明细，后续再单独加 `/analysis/enrichments` 查询接口，但这不属于本轮范围

### Test Plan

- LLM enrichment 单测
  - trial response model 能成功校验合法 JSON schema 输出
  - literature response model 能拒绝缺字段或错类型 JSON
  - evidence snippet 截断与数量上限生效
- scoring 单测
  - rule/LLM/final 三类分数同时生成
  - 四维度融合公式正确
  - trial 与 literature 的 overall 权重不同且计算正确
- pipeline 集成测试
  - `AnalysisPipelineService.build()` 在有 stub LLM client 时能生成 enrichment、bundle 和持久化结果
  - 部分记录 LLM 失败时，阶段 2 仍成功返回，warnings 正确
  - selector 改为使用 `final_scores` 后，章节入选结果可预测
- repository 测试
  - enrichment 表按 `(fetch_run_id, record_key)` upsert/replace 正常
  - analysis snapshot 中包含 `trial_llm_enrichments`、`literature_llm_enrichments`、`llm_enrichment_summary`
- API 测试
  - `/analysis` POST/GET 返回 enrichment summary
  - 前端摘要响应不泄露全量 record-level enrichment payload

### Assumptions

- 使用现有 `LLMClient.generate_structured()` 和当前 provider/factory，不引入新的 provider 抽象
- LLM 增强是同步执行，直接属于 `AnalysisPipelineService` 的一部分
- 当前默认模型来自现有 `MIS_LLM_DEFAULT_MODEL`
- 当前执行策略额外受以下配置控制：
  - `MIS_ANALYSIS_LLM_ENRICHMENT_FULL_SCAN`
  - `MIS_ANALYSIS_LLM_ENRICHMENT_TOP_N`
- 本轮不做异步任务队列、不做批处理合并调用、不做独立重跑 API
- 本轮不把 LLM 结果反写到 `NormalizedTrialRecord` / `NormalizedLiteratureRecord`
- 本轮不做“章节级 LLM 摘要缓存对象”，只做记录级 enrichment + bundle 级聚合
