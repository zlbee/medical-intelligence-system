# 医疗情报系统

医疗情报系统 V1 原型仓库。当前已完成阶段 0 的项目底座与开发环境初始化，包含：

- `FastAPI` 后端骨架
- `React + Vite` 前端骨架
- `Docker Compose` 本地联调环境
- SQLite、日志、配置、健康检查基础设施

## 目录

- `backend/`: 后端服务
- `frontend/`: 前端应用
- `docs/`: 设计与实施文档

## 快速开始

### 1. 准备环境变量（可选）

如需覆盖默认配置，可复制根目录 `.env.example` 为 `.env` 并按需修改；不复制也可直接使用默认值启动。
其中 `MIS_CORS_ORIGINS` 需要使用 JSON 数组格式，例如 `["http://localhost:5173","http://127.0.0.1:5173"]`。

### 2. Docker 启动

```bash
docker compose up --build
```

默认访问地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- 健康检查：`http://localhost:8000/health`

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

## 当前阶段状态

当前处于 [实施阶段拆分与里程碑](D:\Project\REFERENCE\medical-intelligence-system\docs\实施阶段拆分与里程碑.md) 的“阶段 0：项目底座与开发环境初始化”。
