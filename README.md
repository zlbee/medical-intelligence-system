# 医疗情报系统

医疗情报系统是一个面向靶点与适应症调研的原型项目，围绕 `ClinicalTrials.gov + PubMed` 建立从数据采集、结构化分析到 Markdown 报告生成的闭环。仓库内同时包含 `FastAPI` 后端、`React + Vite` 前端，以及用于本地联调的 `Docker Compose` 配置。

## 当前能力

- 双源采集：按靶点、别名、适应症等条件抓取 `ClinicalTrials.gov` 与 `PubMed` 数据
- 原始数据落库：将采集结果保存到 SQLite，支持按采集任务追踪与查询
- 阶段 2 分析：完成标准化、规则评分、统计汇总，并在 LLM 可用时执行记录级增强
- 阶段 3 报告：基于分析快照生成 Markdown 报告，并保存章节引用来源
- 前端工作台：提供健康检查、采集发起、分析构建、报告生成与下载能力

## 目录

- `backend/`：FastAPI 后端服务、数据库访问、采集/分析/报告链路
- `frontend/`：React + Vite 前端工作台
- `docs/`：架构设计、阶段规划、需求说明与示例数据

## 核心流程

1. 发起一次采集任务：`POST /api/fetches`
2. 查看采集结果与原始记录：`GET /api/fetches/{fetch_run_id}`、`GET /api/fetches/{fetch_run_id}/records`
3. 构建分析快照：`POST /api/fetches/{fetch_run_id}/analysis`
4. 生成 Markdown 报告：`POST /api/fetches/{fetch_run_id}/report`

## 环境依赖

### 方案一：Docker 本地联调

- Docker Desktop，或 Docker Engine + Docker Compose 插件

### 方案二：本地开发

- Python `3.12`
- Node.js `20+`
- npm `10+`
- 可访问外部网络
- `ClinicalTrials.gov` 与 `PubMed` 可用网络访问
- 若需要 LLM 增强或阶段 3 报告生成，还需要可访问 `OpenRouter`

说明：

- 项目默认使用 SQLite，无需单独安装数据库服务
- 后端本地默认数据库文件位于 `backend/data/medical_intelligence.db`
- 阶段 3 生成的 Markdown 默认会镜像写入 `backend/reports/`

## 配置步骤

### 1. 准备根目录环境变量

先复制根目录示例配置：

```bash
cp .env.example .env
```

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example .env
```

说明：

- `docker compose` 依赖根目录 `.env` 文件，建议始终先创建
- 后端也会自动读取根目录 `.env`

### 2. 按需修改核心配置

以下变量最常用：

| 变量 | 作用 | 是否必填 |
| --- | --- | --- |
| `MIS_CORS_ORIGINS` | 后端允许访问的前端来源，需使用 JSON 数组格式 | 非必填 |
| `MIS_DATABASE_URL` | 数据库连接串，默认使用 SQLite | 非必填 |
| `MIS_REPORT_OUTPUT_DIR` | Markdown 报告镜像输出目录 | 非必填 |
| `MIS_LLM_API_KEY` | OpenRouter API Key | 阶段 3 必填，阶段 2 可选 |
| `MIS_LLM_DEFAULT_MODEL` | 默认使用的 LLM 模型名 | 阶段 3 必填，阶段 2 可选 |
| `MIS_NCBI_EMAIL` | PubMed 请求的可选联系邮箱标识 | 非必填 |
| `MIS_NCBI_API_KEY` | PubMed 请求的可选 API Key | 非必填 |
| `VITE_API_BASE_URL` | 前端调用后端的基础地址 | 非必填 |

补充说明：

- 当前代码中 `MIS_LLM_PROVIDER` 仅实现了 `openrouter`
- 若未配置 `MIS_LLM_API_KEY` 或 `MIS_LLM_DEFAULT_MODEL`，阶段 2 仍可运行，但会退化为规则评分与缓存复用；阶段 3 报告生成会直接报错
- `MIS_CORS_ORIGINS` 默认值示例：`["http://localhost:5173","http://127.0.0.1:5173"]`

### 3. 按需调整采集与分析参数

以下参数用于控制抓取规模、节流与 LLM 增强策略：

- `MIS_FETCH_CLINICALTRIALS_MAX_RECORDS=500`
- `MIS_FETCH_PUBMED_MAX_RECORDS=200`
- `MIS_FETCH_QUERY_INTERVAL_SECONDS=0.5`
- `MIS_ANALYSIS_LLM_ENRICHMENT_FULL_SCAN=false`
- `MIS_ANALYSIS_LLM_ENRICHMENT_TOP_N=20`

语义说明：

- `page_size`、`retmax`、`batch_size` 表示单轮批大小，不表示总抓取上限
- 实际总抓取量由 `MIS_FETCH_CLINICALTRIALS_MAX_RECORDS` 和 `MIS_FETCH_PUBMED_MAX_RECORDS` 控制
- 当 `MIS_ANALYSIS_LLM_ENRICHMENT_FULL_SCAN=false` 时，只会对规则分更高的记录执行新的 LLM 增强

### 4. 前端本地开发的配置说明

前端本地运行 `npm run dev` 时，不会自动读取仓库根目录 `.env`。默认情况下，前端会直接访问 `http://localhost:8000`。

如果你的后端地址不是默认值，可以在 `frontend/` 目录额外创建 `.env.local`：

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## 启动方式

### 方式一：使用 Docker Compose

```bash
docker compose up --build
```

启动后默认访问地址：

- 前端工作台：`http://localhost:5173`
- 后端 API：`http://localhost:8000`
- 健康检查：`http://localhost:8000/health`
- 采集接口：`http://localhost:8000/api/fetches`

说明：

- 首次启动会自动安装镜像依赖
- 后端服务启动时会自动初始化数据库表
- 代码目录通过 volume 挂载，适合本地联调

### 方式二：本地分别启动前后端

#### 启动后端

```bash
cd backend
python -m venv .venv
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
source .venv/bin/activate
```

安装依赖并启动：

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 启动前端

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 方式三：仅运行已安装依赖后的常用命令

后端测试：

```bash
cd backend
pytest
```

前端构建：

```bash
cd frontend
npm run build
```

## 相关文档

- [架构设计方案](docs/架构设计方案.md)
- [实施阶段拆分与里程碑](docs/实施阶段拆分与里程碑.md)
