# Minerva

Minerva是一个基于现代技术栈构建的企业级智能应用平台，采用FastAPI后端、React前端和PostgreSQL数据库的架构设计。项目以模块化方式组织，具备高度可扩展性和可维护性。

## 核心功能特色：

- **AI智能集成**：内置OpenAI兼容的AI调用模块，支持多种大模型供应商，提供统一的AI服务接口
- **规则引擎系统**：强大的规则管理模块，支持工程代码、审查规则等业务逻辑配置
- **分布式任务调度**：基于Celery的分布式定时任务系统，支持热更新和可视化Cron表达式配置
- **OCR文档处理**：集成多种OCR引擎，支持文件识别和智能文档处理
- **数据字典管理**：统一的数据字典系统，支持多层级分类管理
- **S3云存储集成**：完善的云存储解决方案
- **技术优势**： 项目采用领域驱动设计（DDD）架构，模块间解耦清晰，支持多租户隔离。通过Docker容器化部署，提供完善的开发环境和生产部署方案。Minerva致力于为企业提供智能化的业务处理平台，特别适合需要规则引擎、AI集成和自动化任务调度的应用场景。

## 环境要求

| 依赖 | 说明 |
|------|------|
| Docker | 用于 `docker compose` 启动 PostgreSQL |
| Python | 3.11+ |
| Node.js | 20+ |
| 系统 | 已开放端口 5432、8000、5173 供本机访问 |

## 一、拉代码与基础设施

1. 克隆本仓库，在**仓库根目录**执行，启动数据库：

   ```bash
   docker compose up -d
   ```

2. 确认 `postgres` 容器运行正常（Up）。

## 二、配置环境变量

将 `backend/.env.example` 复制为 `backend/.env`（若仓库根目录另有 `.env.example` 的说明，以 `backend/.env.example` 为准）：

**Linux / macOS：**

```bash
cp backend/.env.example backend/.env.local
```

**Windows (PowerShell)：**

```powershell
Copy-Item backend/.env.example backend/.env.local
```

可选团队 dev 配置：`cp backend/.env.example backend/.env.dev`（使用 `run-backend dev` 时加载）。

`backend/.env.local` 中默认同目录示例即可连接本机 `docker compose` 暴露的库（`127.0.0.1:5432`）。**生产或多人协作时请修改 `JWT_SECRET` 为足够长的随机串。**

## 三、后端：安装依赖与启动

以下命令均在 **`backend` 目录** 下执行（先 `cd backend`）。

### 安装依赖

1. **（推荐）创建并激活虚拟环境**

   **Windows**

   *PowerShell：*

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   *cmd：*

   ```bat
   python -m venv .venv
   .\.venv\Scripts\activate.bat
   ```

   **Linux / macOS：**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **安装项目依赖（可编辑模式，含开发依赖 ruff 等）**

   ```bash
   pip install -e ".[dev]"
   ```

   说明：依赖定义在 `backend/pyproject.toml`；`[dev]` 为可选的开发工具集。若无需开发工具，可只执行 `pip install -e .`。

### 数据库迁移

首次或代码更新后，建议执行 Alembic 迁移，使表结构与当前代码一致（需已配置 `backend/.env.local`（或当前 profile 对应文件）中的 `SYNC_DATABASE_URL` 等）：

```bash
alembic upgrade head
```

### 启动服务

在**已激活虚拟环境**且（如需）已迁移的前提下，用 Uvicorn 热重载启动 API（默认 `http://0.0.0.0:8000`）：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**推荐：** 在**仓库根目录**使用脚本启动（**默认且要求** `backend/.venv` 已创建；`run-backend` / `run-celery` 会使用其中的 Python。若无 venv 会报错并提示建环境；仅在设置 `MINERVA_ALLOW_SYSTEM_PYTHON=1` 时才回退系统 Python）：

1. **API**：`scripts\run-backend.cmd`（Windows）或 `bash scripts/run-backend.sh`（Linux/macOS）— 无参默认加载 `backend/.env.local`；`run-backend dev` 加载 `.env.dev`
2. **Celery**（需 Redis；定时任务另需 Beat）：须显式指定 profile 与子命令，例如：
   - `scripts\run-celery.cmd local worker` 与 `scripts\run-celery.cmd local beat`
   - `bash scripts/run-celery.sh local worker` / `local beat`

**Windows Celery 排错**

- **双终端**：定时任务与「立即执行」须 **Worker、Beat 各开一个终端**；仅开 Worker 时 Beat 不会调度，仅开 Beat 时队列无人消费。
- **Worker 池**：Windows 上 `run-celery.cmd` 默认 **`threads` 池**（`MINERVA_CELERY_POOL`、`MINERVA_CELERY_CONCURRENCY`，默认并发 4）。`MINERVA_CELERY_USE_PREFORK=1` 为兼容旧开关，等价于 `MINERVA_CELERY_POOL=prefork`。
- **假死 / 不消费**：按顺序排查：
  1. Redis 可达（启动脚本会跑 broker 预检；亦可 `cd backend` 后 `python -m app.sys.celery.service.broker_preflight`）。
  2. Beat 终端是否周期性出现 `Scheduler: Sending due task`；Worker 是否 `ready` 且对任务有 `received`。
  3. 队列积压：`redis-cli LLEN celery`（或 `.env` 中 `CELERY_DEFAULT_QUEUE` 所指队列名）是否持续增长。
  4. 单例锁：若日志大量 `already_running`，检查并视情况删除 `minerva:celery:scheduled_singleton:*` 对应 key 后重试「立即执行」。
- **无法 Ctrl+C 退出**：优先执行 `scripts\stop-celery.cmd`（结束 `celery.exe` 及命令行含 `celery -A app.celery_app` 的 Python 进程树）；Linux/macOS 可用 `bash scripts/stop-celery.sh`。
- **可选**：在 WSL2 或 Docker（Linux）内用 `bash scripts/run-celery.sh` 跑 Worker/Beat，Windows 本机仅跑 API 与前端；Broker 在本机 Redis 时需监听 `0.0.0.0` 并将 `CELERY_BROKER_URL` 指向宿主机 IP。

可选：`MINERVA_BACKEND_PORT` 覆盖 API 端口（默认 8000）。

**排错（Windows + Python 3.13）：** 若报 `No module named 'pydantic_core._pydantic_core'`，多因启动或 `pip` 实际使用了 **3.13t**（`python3.13t.exe`）而 `pydantic-core` 无对应预编译包。请用 **标准 3.13** 建 venv 并装依赖：``py -3.13 -m venv .venv``，激活后再 ``pip install -e ".[dev]"``；或全局安装/修复时用 ``py -3.13 -m pip install --force-reinstall "pydantic" "pydantic-core"``，不要在此时使用 ``py -3 -m pip``（可能仍指向 3.13t）。

成功后可访问接口文档： [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) ，健康检查： [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz) 。业务 API 统一前缀 **`/api`**（如 `POST /api/auth/login`）。

**生产部署**：前端 `npm run build` 后，可参考 `scripts/nginx/minerva.conf` 配置 Nginx（`/api/*` 转发后端，静态资源托管 `frontend/dist`）。

**说明：**

- 后端按 `APP_ENV` 读取单个 `backend/.env.<profile>`（如 `.env.local`）中的 `DATABASE_URL`、`SYNC_DATABASE_URL`（Alembic 使用同步 URL）、JWT 等配置。
- 与前端联调时，在 `APP_ENV` 为 dev/development/local/test 时，CORS 允许 `http://localhost` 与 `http://127.0.0.1` 的**任意端口**（便于 Vite 占用 5174 等）；生产环境请按需收紧并仅列出真实站点来源。

## 四、启动前端

另开一个终端，在 **`frontend` 目录** 下操作：

1. 复制前端环境文件（若尚不存在）：

   **Windows (PowerShell)：**

   ```powershell
   cd frontend
   Copy-Item .env.example .env
   ```

   **Linux / macOS：**

   ```bash
   cd frontend
   cp .env.dev.example .env.dev
   ```

2. 确认 `.env` 中 `VITE_API_BASE_URL`：
   - **开发（推荐）**：留空，走 Vite 代理 `/api` → 后端
   - **浏览器直连后端调试**：可设为 `http://127.0.0.1:8000`（仍通过 `VITE_API_PATH_PREFIX=/api` 拼接路径）

   ```env
   # VITE_API_BASE_URL=
   # VITE_API_PATH_PREFIX=/api
   ```

3. 安装依赖并启动开发服务器：

   ```bash
   npm install
   npm run dev
   ```

4. 浏览器打开终端中提示的地址（默认多为 [http://127.0.0.1:5173](http://127.0.0.1:5173) ），在页面中**注册/登录**后使用已接入的功能模块。

5. 生产构建：

   ```bash
   npm run build:production   # 加载 .env.production
   npm run build:test         # 加载 .env.test
   ```

   `npm run build` 等同于 `build:production`。

   输出在 `frontend/dist/`，可交由 Nginx 等静态服务器托管；参考 `scripts/nginx/minerva.conf`。

## 五、服务与地址一览

| 服务 | 默认地址 | 说明 |
|------|----------|------|
| 前端 (Vite) | http://127.0.0.1:5173 | 见 `frontend` 的 `npm run dev` 输出 |
| 后端 API | http://127.0.0.1:8000 | FastAPI；Swagger `/docs`；业务接口 `/api/*` |
| PostgreSQL | 127.0.0.1:5432 | 用户/库/密码与 `docker-compose.yml` 一致时可用 `backend/.env.example` 默认连接串 |

## 使用说明（简要）

- 登录/注册 调用 `POST /api/auth/login`、`/api/auth/register`；当前工作空间 ID 在 JWT 的 `wid` 声明中，前端会据此请求需授权的后端资源。

## 六、知识库（Dataset / 智库）

前端路由：`/app/dataset`（旧路径 `/app/knowledge-base` 会重定向）。后端模块：`backend/app/dataset/`。

### 依赖与向量库

1. **PostgreSQL pgvector**：高质量索引默认使用 `DATASET_VECTOR_STORE=pgvector`。需在数据库中启用扩展（迁移 `g7h8i9j0k1l2` 会尝试 `CREATE EXTENSION vector`）。若 Alembic 历史链与本地库不一致，可先 `alembic stamp f6a7b8c9d0e1` 再 `alembic upgrade head`，或对照 `backend/alembic/versions/g7h8i9j0k1l2_dataset_tables.py` 手动建表。
2. **可选向量后端**：Qdrant / Weaviate 需安装 `pip install -e ".[vector]"` 并配置 `DATASET_QDRANT_*` 或 `DATASET_WEAVIATE_*`（见 `backend/.env.example`）。
3. **Embedding 模型**：高质量模式需在「模型供应商」中配置可用的 **Embeddings** 模型。

### Celery 索引队列

文档解析与向量化由 Celery 异步执行。`run-celery` 脚本默认让 Worker 监听 **`default,dataset`** 队列（可通过 `MINERVA_CELERY_QUEUES` 覆盖），例如：

```bash
# 仓库根目录
scripts\run-celery.cmd local worker
bash scripts/run-celery.sh local worker
```

未消费 `dataset` 队列时，上传文档会一直处于 `waiting` / `indexing` 状态。

### 环境变量（节选）

| 变量 | 说明 |
|------|------|
| `DATASET_VECTOR_STORE` | `pgvector`（默认）/ `qdrant` / `weaviate` |
| `DATASET_PGVECTOR_URL` | 留空则复用 `SYNC_DATABASE_URL` |
| `DATASET_BATCH_UPLOAD_LIMIT` | 单次批量上传文档数上限 |
| `DATASET_SINGLE_FILE_SIZE_LIMIT_MB` | 单文件大小上限（MB） |

### 测试

```bash
cd backend
pytest tests/ -k dataset -q
```

可选全链路集成测试（需 DB、pgvector、Celery Worker、`EMBEDDINGS` 模型）：设置 `RUN_DATASET_INTEGRATION=1` 后运行 `tests/test_dataset_integration.py`。

## 七、知识图谱（GraphKB / GraphRAG · LightRAG）

独立于 Dataset 的知识图谱模块。前端菜单「知识图谱」，路由 `/app/graph-kb`（列表 / 创建 / 文档 / 图浏览 / 摘要 / 问答 / 设置）。后端：`backend/app/graph_kb/`；权限码 `feature:graph_kb`。

### Celery 队列 `graph_kb`

索引与引擎 namespace 清理走 Celery 队列 **`graph_kb`**（`run-celery` 默认 `MINERVA_CELERY_QUEUES` 已含 `default,dataset,graph_kb`）。未消费该队列时，索引任务会一直处于排队/进行中。

```bash
# 仓库根目录
scripts\run-celery.cmd local worker
bash scripts/run-celery.sh local worker
```

### 独立引擎 Worker

主 API **不** import GraphRAG / LightRAG SDK；通过 HTTP 调用独立进程（`GraphEngineClient`）。两套引擎装在**各自 Worker 的独立 venv**，避免与主后端依赖冲突。

| Worker | 脚本 | 默认地址 |
|--------|------|----------|
| LightRAG | `scripts/run-graph-kb-lightrag-worker.cmd` | `http://127.0.0.1:8101` |
| GraphRAG | `scripts/run-graph-kb-graphrag-worker.cmd` | `http://127.0.0.1:8102` |

**安装真实引擎依赖**（各 Worker 目录下创建 `.venv` 并安装 `.[dev,engine]`）：

```bash
# 仓库根目录 — 安装 LightRAG + GraphRAG 两个 Worker
bash scripts/install-graph-kb-workers.sh
scripts\install-graph-kb-workers.cmd

# 仅安装其中一个
MINERVA_GRAPH_KB_WORKERS=lightrag bash scripts/install-graph-kb-workers.sh
set MINERVA_GRAPH_KB_WORKERS=lightrag && scripts\install-graph-kb-workers.cmd
```

| Worker | 引擎包（pinned） | 说明 |
|--------|------------------|------|
| LightRAG | `lightrag-hku==1.5.6` + `asyncpg` / `pgvector` | PG 存储后端（KV / 向量 / 图 / doc status） |
| GraphRAG | `graphrag==3.1.2` + `pandas` / `pyarrow` | 含 CLI `graphrag index` 与 parquet 导出读取 |

Worker 侧可用 `GRAPH_KB_WORKER_FAKE=1` 跳过真实引擎 SDK（内存假实现，便于无 GPU/无 SDK 的本地与 CI）。**未设置 fake 时**，启动脚本要求已执行上述 install（使用 `workers/graph-kb-*/.venv`）。存储隔离按 `(workspace_id, graph_id)`；LightRAG workspace 字符串 / GraphRAG 根目录**只在 Worker 内拼接**。

### 环境变量（节选）

| 变量 | 说明 |
|------|------|
| `GRAPH_KB_ENGINE_CLIENT` | `http`（默认，调独立 Worker）/ `fake`（进程内 Fake，**单元测试推荐**） |
| `GRAPH_KB_LIGHTRAG_WORKER_URL` | LightRAG Worker 基址（默认 `http://127.0.0.1:8101`） |
| `GRAPH_KB_GRAPHRAG_WORKER_URL` | GraphRAG Worker 基址（默认 `http://127.0.0.1:8102`） |
| `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` | LightRAG Worker Bearer 认证（`http` 模式必填） |
| `GRAPH_KB_GRAPHRAG_WORKER_API_KEY` | GraphRAG Worker Bearer 认证（`http` 模式必填） |
| `GRAPH_KB_LIGHTRAG_DATABASE_URL` | LightRAG 专用库；**禁止**复用 `MEM0_*` |
| `GRAPH_KB_DATA` | GraphRAG 数据根目录；空则 `<cwd>/data/graph_kb` |
| `GRAPH_KB_JOB_TIMEOUT_SECONDS` | 索引/清理 Celery 超时（默认 7200） |

本地开发时，Worker 进程须 export 与 `backend/.env.dev` 相同的 `GRAPH_KB_*_WORKER_API_KEY`。

### 测试

```bash
cd backend
# 推荐：进程内 Fake，无需启动 Worker
set GRAPH_KB_ENGINE_CLIENT=fake   # PowerShell: $env:GRAPH_KB_ENGINE_CLIENT="fake"
pytest tests/test_graph_kb_*.py -q
```

## 参与贡献

1. Fork 本仓库并新建功能分支。  
2. 提交前建议在后端目录执行 `ruff check .`，在 `frontend` 执行 `npm run build` 作基本校验。  
3. 通过 Pull Request 合并。
