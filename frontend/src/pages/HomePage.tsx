import { useEffect, useState } from "react";

import { fetchHealth } from "../services/healthApi";
import type { HealthResponse } from "../types/health";

type LoadState = "idle" | "loading" | "success" | "error";

export function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");

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

  return (
    <main className="page-shell">
      <section className="hero-card">
        <div className="eyebrow">Medical Intelligence System</div>
        <h1>医疗情报系统</h1>
        <p className="lead">
          阶段 0 已完成项目底座初始化。当前页面用于验证前端骨架、路由和后端健康检查是否连通。
        </p>
      </section>

      <section className="grid">
        <article className="panel">
          <h2>阶段 0 已落地内容</h2>
          <ul>
            <li>FastAPI 后端入口与健康检查接口</li>
            <li>配置、日志、SQLite 初始化脚手架</li>
            <li>React + Vite 前端骨架与路由</li>
            <li>Docker Compose 本地联调环境</li>
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
    </main>
  );
}

