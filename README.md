# 医疗情报系统

医疗情报系统 V1 原型仓库。当前已完成阶段 0 的项目底座初始化，并已进入阶段 1 的双源采集实现，包含：

- `FastAPI` 后端骨架
- `React + Vite` 前端骨架
- `Docker Compose` 本地联调环境
- SQLite、日志、配置、健康检查基础设施
- `ClinicalTrials.gov + PubMed` 双源采集链路
- 原始数据入库与 JSON 查询配置接口

## 目录

- `backend/`: 后端服务
- `frontend/`: 前端应用
- `docs/`: 设计与实施文档

## 快速开始

### 1. 准备环境变量（可选）

如需覆盖默认配置，可复制根目录 `.env.example` 为 `.env` 并按需修改；不复制也可直接使用默认值启动。
其中 `MIS_CORS_ORIGINS` 需要使用 JSON 数组格式，例如 `["http://localhost:5173","http://127.0.0.1:5173"]`。
阶段 2 的 LLM 增强还支持两项控制：

- `MIS_ANALYSIS_LLM_ENRICHMENT_FULL_SCAN=true`
  默认全量逐条做记录级 LLM 增强
- `MIS_ANALYSIS_LLM_ENRICHMENT_TOP_N=20`
  当 `FULL_SCAN=false` 时生效，表示 trial 和 literature 各自只对规则分排名前 `N` 条记录执行 LLM 增强

### 2. Docker 启动

```bash
docker compose up --build
```

默认访问地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- 健康检查：`http://localhost:8000/health`
- 多源采集接口：`http://localhost:8000/api/fetches`

### 3. 本地开发

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## 阶段 1 API

### 创建一次多源采集任务

```text
POST /api/fetches
```

请求体可使用 JSON 配置两个来源的筛选条件，示例文件见：

- [示例采集请求-HER2.json](D:\Project\REFERENCE\medical-intelligence-system\docs\示例采集请求-HER2.json)

### 查询采集任务详情

```text
GET /api/fetches/{fetch_run_id}
```

### 查询采集到的原始记录

```text
GET /api/fetches/{fetch_run_id}/records
GET /api/fetches/{fetch_run_id}/records?source_name=pubmed
```

## 当前阶段状态

当前正在实施 [实施阶段拆分与里程碑](D:\Project\REFERENCE\medical-intelligence-system\docs\实施阶段拆分与里程碑.md) 的“阶段 1：多源采集与原始数据入库”。
