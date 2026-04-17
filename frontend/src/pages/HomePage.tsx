import { useEffect, useState, type FormEvent } from "react";

import { createFetchRun, listRawRecords } from "../services/fetchApi";
import { fetchHealth } from "../services/healthApi";
import type { FetchRunResponse, RawRecord } from "../types/fetch";
import type { HealthResponse } from "../types/health";

type LoadState = "idle" | "loading" | "success" | "error";
type SubmitState = "idle" | "submitting" | "success" | "error";

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
          </div>
        )}
      </section>
    </main>
  );
}
