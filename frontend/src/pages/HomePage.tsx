import { useEffect, useState, type FormEvent } from "react";

import {
  buildAnalysisBundle,
  createFetchRun,
  getAnalysisBundle,
  listRawRecords,
} from "../services/fetchApi";
import { fetchHealth } from "../services/healthApi";
import type {
  AnalysisBundleResponse,
  FetchRunResponse,
  NamedCount,
  RawRecord,
  WarningItem,
} from "../types/fetch";
import type { HealthResponse } from "../types/health";

type LoadState = "idle" | "loading" | "success" | "error";
type SubmitState = "idle" | "submitting" | "success" | "error";
type AnalysisState = "idle" | "loading" | "success" | "error";

function formatDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}/${month}/${day}`;
}

function formatClinicalTrialsDate(date: Date): string {
  return formatDate(date).replaceAll("/", "-");
}

const today = new Date();
const oneYearAgo = new Date(today);
oneYearAgo.setFullYear(today.getFullYear() - 1);

const defaultSourceConfigs = JSON.stringify(
  {
    clinicaltrials: {
      enabled: true,
      page_size: 5,
      max_pages: 1,
      count_total: true,
      query: {
        intr: "HER2",
        term: `(AREA[Phase]\"Phase 2\" OR AREA[Phase]\"Phase 3\") AND AREA[LastUpdatePostDate]RANGE[${formatClinicalTrialsDate(oneYearAgo)}, MAX]`,
      },
      filters: {
        overallStatus: ["RECRUITING", "ACTIVE_NOT_RECRUITING"],
      },
    },
    pubmed: {
      enabled: true,
      retmax: 5,
      batch_size: 5,
      sort: "pub_date",
      filters: {
        publication_types: ["Clinical Trial"],
        extra_terms: [
          "(\"phase ii\"[Title/Abstract] OR \"phase iii\"[Title/Abstract] OR \"phase 2\"[Title/Abstract] OR \"phase 3\"[Title/Abstract])",
        ],
        date_from: formatDate(oneYearAgo),
        date_to: formatDate(today),
        has_abstract: true,
      },
    },
  },
  null,
  2,
);

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatCountMap(values: Record<string, number>, limit = 5): string {
  const entries = Object.entries(values);
  if (!entries.length) {
    return "暂无";
  }
  return entries
    .slice(0, limit)
    .map(([name, count]) => `${name}: ${count}`)
    .join(" / ");
}

function formatNamedCounts(items: NamedCount[], limit = 4): string {
  if (!items.length) {
    return "暂无";
  }
  return items
    .slice(0, limit)
    .map((item) => `${item.name} (${item.count})`)
    .join(" / ");
}

type WarningSummary = {
  key: string;
  message: string;
  count: number;
  errorType: string | null;
  errorText: string | null;
};

function summarizeWarnings(warnings: WarningItem[]): WarningSummary[] {
  const summaryMap = new Map<string, WarningSummary>();

  for (const warning of warnings) {
    const errorType =
      typeof warning.details.error_type === "string" ? warning.details.error_type : null;
    const errorText =
      typeof warning.details.error === "string" ? warning.details.error : null;
    const key = [warning.code, warning.message, errorType ?? "", errorText ?? ""].join("|");
    const existing = summaryMap.get(key);

    if (existing) {
      existing.count += 1;
      continue;
    }

    // Stage 2 may emit one warning per failed record. We aggregate identical failures
    // so the UI stays readable while still surfacing the underlying cause.
    summaryMap.set(key, {
      key,
      message: warning.message,
      count: 1,
      errorType,
      errorText,
    });
  }

  return Array.from(summaryMap.values());
}

export function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [submitError, setSubmitError] = useState<string>("");
  const [target, setTarget] = useState("HER2");
  const [indication, setIndication] = useState("breast cancer");
  const [aliases, setAliases] = useState("ERBB2");
  const [sourceConfigText, setSourceConfigText] = useState(defaultSourceConfigs);
  const [fetchResult, setFetchResult] = useState<FetchRunResponse | null>(null);
  const [rawRecords, setRawRecords] = useState<RawRecord[]>([]);
  const [analysisState, setAnalysisState] = useState<AnalysisState>("idle");
  const [analysisError, setAnalysisError] = useState("");
  const [analysisResult, setAnalysisResult] = useState<AnalysisBundleResponse | null>(
    null,
  );
  const warningSummaries = analysisResult
    ? summarizeWarnings(analysisResult.warnings)
    : [];

  useEffect(() => {
    let isMounted = true;

    async function loadHealth() {
      setLoadState("loading");
      try {
        const response = await fetchHealth();
        if (!isMounted) {
          return;
        }
        setHealth(response);
        setLoadState("success");
      } catch (error) {
        if (!isMounted) {
          return;
        }
        const message =
          error instanceof Error ? error.message : "无法连接后端健康检查接口。";
        setErrorMessage(message);
        setLoadState("error");
      }
    }

    loadHealth();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError("");
    setSubmitState("submitting");
    setFetchResult(null);
    setRawRecords([]);
    setAnalysisState("idle");
    setAnalysisError("");
    setAnalysisResult(null);

    try {
      const sourceConfigs = JSON.parse(sourceConfigText) as Record<string, unknown>;
      const payload = {
        target,
        indication,
        aliases: aliases
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        source_configs: sourceConfigs,
      };
      const created = await createFetchRun(payload);
      const recordsResponse = await listRawRecords(created.fetch_run_id);
      setFetchResult(created);
      setRawRecords(recordsResponse.items);
      setSubmitState("success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "采集请求执行失败。";
      setSubmitError(message);
      setSubmitState("error");
    }
  }

  async function handleBuildAnalysis() {
    if (!fetchResult) {
      return;
    }
    setAnalysisError("");
    setAnalysisState("loading");

    try {
      const built = await buildAnalysisBundle(fetchResult.fetch_run_id);
      setAnalysisResult(built);
      setAnalysisState("success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "阶段 2 分析执行失败。";
      setAnalysisError(message);
      setAnalysisState("error");
    }
  }

  async function handleLoadExistingAnalysis() {
    if (!fetchResult) {
      return;
    }
    setAnalysisError("");
    setAnalysisState("loading");

    try {
      const loaded = await getAnalysisBundle(fetchResult.fetch_run_id);
      setAnalysisResult(loaded);
      setAnalysisState("success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "分析快照查询失败。";
      setAnalysisError(message);
      setAnalysisState("error");
    }
  }

  return (
    <main className="page-shell">
      <section className="hero-card">
        <div className="eyebrow">Medical Intelligence System</div>
        <h1>医疗情报系统</h1>
        <p className="lead">
          阶段 1 已接入多源采集链路。当前页面既能验证前后端连通，也能直接提交靶点和 JSON
          查询配置，查看原始采集结果。
        </p>
      </section>

      <section className="grid">
        <article className="panel">
          <h2>当前已落地内容</h2>
          <ul>
            <li>FastAPI 后端入口与健康检查接口</li>
            <li>配置、日志、SQLite 初始化脚手架</li>
            <li>React + Vite 前端骨架与路由</li>
            <li>Docker Compose 本地联调环境</li>
            <li>ClinicalTrials.gov 与 PubMed 双源采集接口</li>
          </ul>
        </article>

        <article className="panel">
          <h2>后端健康状态</h2>
          {loadState === "loading" && <p>正在检测后端服务状态...</p>}
          {loadState === "error" && (
            <p className="status status-error">检测失败：{errorMessage}</p>
          )}
          {loadState === "success" && health && (
            <div className="status-stack">
              <div className="status status-ok">
                服务状态：{health.status} / 数据库：{health.database.status}
              </div>
              <dl className="meta-list">
                <div>
                  <dt>服务名称</dt>
                  <dd>{health.service}</dd>
                </div>
                <div>
                  <dt>环境</dt>
                  <dd>{health.environment}</dd>
                </div>
                <div>
                  <dt>版本</dt>
                  <dd>{health.version}</dd>
                </div>
                <div>
                  <dt>数据库</dt>
                  <dd>{health.database.detail}</dd>
                </div>
              </dl>
            </div>
          )}
        </article>
      </section>

      <section className="panel playground-panel">
        <h2>阶段 1 采集调试面板</h2>
        <p className="panel-intro">
          这里可以直接输入靶点，并使用 JSON 配置两个来源的查询筛选条件。
        </p>
        <form className="fetch-form" onSubmit={handleSubmit}>
          <label>
            <span>靶点</span>
            <input value={target} onChange={(event) => setTarget(event.target.value)} />
          </label>
          <label>
            <span>适应症</span>
            <input
              value={indication}
              onChange={(event) => setIndication(event.target.value)}
            />
          </label>
          <label>
            <span>别名（逗号分隔）</span>
            <input value={aliases} onChange={(event) => setAliases(event.target.value)} />
          </label>
          <label>
            <span>来源配置 JSON</span>
            <textarea
              rows={18}
              value={sourceConfigText}
              onChange={(event) => setSourceConfigText(event.target.value)}
            />
          </label>
          <button type="submit" disabled={submitState === "submitting"}>
            {submitState === "submitting" ? "正在采集..." : "执行多源采集"}
          </button>
        </form>

        {submitState === "error" && (
          <p className="status status-error">执行失败：{submitError}</p>
        )}

        {fetchResult && (
          <div className="result-stack">
            <div className="status status-ok">
              采集完成：{fetchResult.status}，原始记录 {fetchResult.raw_record_count} 条
            </div>

            <div className="result-grid">
              <article className="result-card">
                <h3>采集任务摘要</h3>
                <dl className="meta-list">
                  <div>
                    <dt>任务 ID</dt>
                    <dd>{fetchResult.fetch_run_id}</dd>
                  </div>
                  <div>
                    <dt>靶点</dt>
                    <dd>{fetchResult.target}</dd>
                  </div>
                  <div>
                    <dt>warning 数量</dt>
                    <dd>{fetchResult.warnings.length}</dd>
                  </div>
                </dl>
              </article>

              <article className="result-card">
                <h3>来源抓取结果</h3>
                <ul className="result-list">
                  {fetchResult.source_results.map((item) => (
                    <li key={item.source_name}>
                      <strong>{item.source_name}</strong>
                      <span>
                        {item.success ? "成功" : "失败"}，抓取 {item.fetched_count} 条
                        {item.total_count !== null ? ` / 总量 ${item.total_count}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </article>
            </div>

            <article className="result-card">
              <h3>原始记录样本</h3>
              <ul className="record-list">
                {rawRecords.map((record) => (
                  <li key={record.record_id}>
                    <div className="record-head">
                      <strong>{record.source_name}</strong>
                      <span>{record.source_id}</span>
                    </div>
                    {record.source_url && (
                      <a href={record.source_url} target="_blank" rel="noreferrer">
                        {record.source_url}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </article>

            <article className="result-card">
              <h3>阶段 2 分析</h3>
              <p className="panel-intro">
                在阶段 1 的原始记录基础上执行标准化、统计与章节输入构建。
              </p>
              <div className="action-row">
                <button
                  type="button"
                  className="action-button"
                  onClick={handleBuildAnalysis}
                  disabled={analysisState === "loading"}
                >
                  {analysisState === "loading"
                    ? "正在构建分析快照..."
                    : analysisResult
                      ? "重新构建阶段 2 分析"
                      : "执行阶段 2 分析"}
                </button>
                <button
                  type="button"
                  className="action-button action-button-secondary"
                  onClick={handleLoadExistingAnalysis}
                  disabled={analysisState === "loading"}
                >
                  读取已保存分析快照
                </button>
              </div>

              {analysisState === "error" && (
                <p className="status status-error">执行失败：{analysisError}</p>
              )}

              {analysisResult && (
                <div className="analysis-stack">
                  <div className="status status-ok">
                    分析快照已生成：试验 {analysisResult.global_stats.total_trial_count} 条，
                    文献 {analysisResult.global_stats.total_literature_count} 条，构建时间{" "}
                    {formatDateTime(analysisResult.built_at)}
                  </div>

                  <div className="result-grid">
                    <article className="result-card analysis-card">
                      <h3>分析摘要</h3>
                      <dl className="meta-list">
                        <div>
                          <dt>Bundle ID</dt>
                          <dd>{analysisResult.bundle_id}</dd>
                        </div>
                        <div>
                          <dt>靶点</dt>
                          <dd>{analysisResult.query.target}</dd>
                        </div>
                        <div>
                          <dt>缺失章节</dt>
                          <dd>
                            {analysisResult.coverage.missing_dimensions.length
                              ? analysisResult.coverage.missing_dimensions.join(" / ")
                              : "无"}
                          </dd>
                        </div>
                      </dl>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>全局统计</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>阶段分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.global_stats.trial_phase_distribution,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>主要 Sponsor</strong>
                          <span>
                            {formatNamedCounts(analysisResult.global_stats.top_sponsors)}
                          </span>
                        </li>
                        <li>
                          <strong>文献年份分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.global_stats.publication_count_by_year,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>高频期刊</strong>
                          <span>
                            {formatNamedCounts(analysisResult.global_stats.top_journals)}
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>Coverage 与 Warning</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>Target Overview</strong>
                          <span>
                            {analysisResult.coverage.has_target_overview_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                        <li>
                          <strong>Pipeline Overview</strong>
                          <span>
                            {analysisResult.coverage.has_pipeline_overview_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                        <li>
                          <strong>Research Update</strong>
                          <span>
                            {analysisResult.coverage.has_research_update_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                        <li>
                          <strong>Competition Assessment</strong>
                          <span>
                            {analysisResult.coverage.has_competition_assessment_evidence
                              ? "已覆盖"
                              : "缺少证据"}
                          </span>
                        </li>
                      </ul>
                      {warningSummaries.length > 0 && (
                        <ul className="tag-list">
                          {warningSummaries.map((warning) => (
                            <li key={warning.key} className="tag">
                              {warning.message}
                              {warning.count > 1 ? ` (${warning.count} 次)` : ""}
                              {warning.errorText
                                ? ` 原因：${warning.errorType ?? "UnknownError"} - ${warning.errorText}`
                                : ""}
                            </li>
                          ))}
                        </ul>
                      )}
                    </article>
                  </div>

                  <div className="result-grid">
                    <article className="result-card analysis-card">
                      <h3>章节 1：靶点概述输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>试验证据</strong>
                          <span>{analysisResult.section_inputs.target_overview.trial_keys.length} 条</span>
                        </li>
                        <li>
                          <strong>文献证据</strong>
                          <span>
                            {analysisResult.section_inputs.target_overview.literature_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>别名</strong>
                          <span>
                            {analysisResult.section_inputs.target_overview.facts.alias_terms.join(
                              " / ",
                            ) || "暂无"}
                          </span>
                        </li>
                        <li>
                          <strong>代表性文献</strong>
                          <span>
                            {analysisResult.section_inputs.target_overview.facts.representative_paper_keys.length} 条
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>章节 2：在研管线概览输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>试验证据</strong>
                          <span>
                            {analysisResult.section_inputs.pipeline_overview.trial_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>阶段分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.section_inputs.pipeline_overview.facts.phase_distribution,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>主要 Sponsor</strong>
                          <span>
                            {formatNamedCounts(
                              analysisResult.section_inputs.pipeline_overview.facts.top_sponsors,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>活跃试验数</strong>
                          <span>
                            {analysisResult.section_inputs.pipeline_overview.facts.active_trial_count}
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>章节 3：近期研究动态输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>文献证据</strong>
                          <span>
                            {analysisResult.section_inputs.research_update.literature_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>年份分布</strong>
                          <span>
                            {formatCountMap(
                              analysisResult.section_inputs.research_update.facts.publication_count_by_year,
                            )}
                          </span>
                        </li>
                        <li>
                          <strong>近期文献</strong>
                          <span>
                            {analysisResult.section_inputs.research_update.facts.recent_paper_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>高价值文献</strong>
                          <span>
                            {analysisResult.section_inputs.research_update.facts.high_value_paper_keys.length} 条
                          </span>
                        </li>
                      </ul>
                    </article>

                    <article className="result-card analysis-card">
                      <h3>章节 4：竞争格局判断输入</h3>
                      <ul className="compact-list">
                        <li>
                          <strong>试验证据</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.trial_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>文献证据</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.literature_keys.length} 条
                          </span>
                        </li>
                        <li>
                          <strong>活跃 Sponsor</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.facts.active_sponsor_count}
                          </span>
                        </li>
                        <li>
                          <strong>后期项目数</strong>
                          <span>
                            {analysisResult.section_inputs.competition_assessment.facts.late_stage_trial_count}
                          </span>
                        </li>
                      </ul>
                    </article>
                  </div>

                  {(analysisResult.section_inputs.target_overview.truncation_notes.length > 0 ||
                    analysisResult.section_inputs.pipeline_overview.truncation_notes.length > 0 ||
                    analysisResult.section_inputs.research_update.truncation_notes.length > 0 ||
                    analysisResult.section_inputs.competition_assessment.truncation_notes.length > 0) && (
                    <article className="result-card analysis-card">
                      <h3>裁剪说明</h3>
                      <ul className="compact-list">
                        {analysisResult.section_inputs.target_overview.truncation_notes.map((note) => (
                          <li key={`target-${note}`}>
                            <strong>靶点概述</strong>
                            <span>{note}</span>
                          </li>
                        ))}
                        {analysisResult.section_inputs.pipeline_overview.truncation_notes.map((note) => (
                          <li key={`pipeline-${note}`}>
                            <strong>在研管线</strong>
                            <span>{note}</span>
                          </li>
                        ))}
                        {analysisResult.section_inputs.research_update.truncation_notes.map((note) => (
                          <li key={`research-${note}`}>
                            <strong>研究动态</strong>
                            <span>{note}</span>
                          </li>
                        ))}
                        {analysisResult.section_inputs.competition_assessment.truncation_notes.map((note) => (
                          <li key={`competition-${note}`}>
                            <strong>竞争格局</strong>
                            <span>{note}</span>
                          </li>
                        ))}
                      </ul>
                    </article>
                  )}
                </div>
              )}
            </article>
          </div>
        )}
      </section>
    </main>
  );
}
