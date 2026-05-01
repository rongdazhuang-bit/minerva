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
cp backend/.env.example backend/.env
```

**Windows (PowerShell)：**

```powershell
Copy-Item backend/.env.example backend/.env
```

`backend/.env` 中默认同目录示例即可连接本机 `docker compose` 暴露的库（`127.0.0.1:5432`）。**生产或多人协作时请修改 `JWT_SECRET` 为足够长的随机串。**

## 三、后端：安装依赖与启动

以下命令均在 **`backend` 目录** 下执行（先 `cd backend`）。

### 安装依赖

1. **（推荐）创建并激活虚拟环境**

   **Windows**

   *PowerShell：*

   ```powershell
   python -m venv minerva
   .\minerva\Scripts\Activate.ps1
   ```

   *cmd：*

   ```bat
   python -m venv minerva
   .\minerva\Scripts\activate.bat
   ```

   **Linux / macOS：**

   ```bash
   python3 -m venv minerva
   source minerva/bin/activate
   ```

2. **安装项目依赖（可编辑模式，含开发依赖 ruff、pytest 等）**

   ```bash
   pip install -e ".[dev]"
   ```

   说明：依赖定义在 `backend/pyproject.toml`；`[dev]` 为可选的开发工具集。若无需开发工具，可只执行 `pip install -e .`。

### 数据库迁移

首次或代码更新后，建议执行 Alembic 迁移，使表结构与当前代码一致（需已配置 `backend/.env` 中的 `SYNC_DATABASE_URL` 等）：

```bash
alembic upgrade head
```

### 启动服务

在**已激活虚拟环境**且（如需）已迁移的前提下，用 Uvicorn 热重载启动 API（默认 `http://0.0.0.0:8000`）：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**可选：** 在**仓库根目录**也可使用脚本快速启动（会优先使用 `backend/.venv` 中的 Python；无 venv 时 Windows 依次尝试 `py -3.13` / `py -3.12` / `py -3.11` 与 `python`，**避免**使用易选中「3.13 自由线程版」的 `py -3`），端口可用 `MINERVA_BACKEND_PORT` 覆盖，默认 8000：

- Windows：`scripts\run-backend.cmd`
- Linux / macOS：`bash scripts/run-backend.sh`（或 `chmod +x` 后直接执行）

**排错（Windows + Python 3.13）：** 若报 `No module named 'pydantic_core._pydantic_core'`，多因启动或 `pip` 实际使用了 **3.13t**（`python3.13t.exe`）而 `pydantic-core` 无对应预编译包。请用 **标准 3.13** 建 venv 并装依赖：``py -3.13 -m venv .venv``，激活后再 ``pip install -e ".[dev]"``；或全局安装/修复时用 ``py -3.13 -m pip install --force-reinstall "pydantic" "pydantic-core"``，不要在此时使用 ``py -3 -m pip``（可能仍指向 3.13t）。

成功后可访问接口文档： [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) ，健康检查： [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz) 。

**说明：**

- 后端会读取 `backend/.env` 中的 `DATABASE_URL`、`SYNC_DATABASE_URL`（Alembic 使用同步 URL）、JWT 等配置。
- 与前端联调时，在 `APP_ENV` 为 dev/development/local/test 时，CORS 允许 `http://localhost` 与 `http://127.0.0.1` 的**任意端口**（便于 Vite 占用 5174 等）；生产环境请按需收紧并仅列出真实站点来源。

## 四、启动前端

另开一个终端，在 **`minerva-ui` 目录** 下操作：

1. 复制前端环境文件（若尚不存在）：

   **Windows (PowerShell)：**

   ```powershell
   cd minerva-ui
   Copy-Item .env.example .env
   ```

   **Linux / macOS：**

   ```bash
   cd minerva-ui
   cp .env.example .env
   ```

2. 确认 `.env` 中 `VITE_API_BASE_URL` 指向本机 API，例如：

   ```env
   VITE_API_BASE_URL=http://127.0.0.1:8000
   ```

3. 安装依赖并启动开发服务器：

   ```bash
   npm install
   npm run dev
   ```

4. 浏览器打开终端中提示的地址（默认多为 [http://127.0.0.1:5173](http://127.0.0.1:5173) ），在页面中**注册/登录**后使用已接入的功能模块。

5. 生产构建立：

   ```bash
   npm run build
   ```

   输出在 `minerva-ui/dist/`，可交由任意静态资源服务器或反向代理到后端。

## 五、服务与地址一览

| 服务 | 默认地址 | 说明 |
|------|----------|------|
| 前端 (Vite) | http://127.0.0.1:5173 | 见 `minerva-ui` 的 `npm run dev` 输出 |
| 后端 API | http://127.0.0.1:8000 | FastAPI，Swagger 见 `/docs` |
| PostgreSQL | 127.0.0.1:5432 | 用户/库/密码与 `docker-compose.yml` 一致时可用 `backend/.env.example` 默认连接串 |

## 使用说明（简要）

- 登录/注册 调用 `POST /auth/login`、`/auth/register`；当前工作空间 ID 在 JWT 的 `wid` 声明中，前端会据此请求需授权的后端资源。

## 参与贡献

1. Fork 本仓库并新建功能分支。  
2. 提交前建议在后端目录执行 `ruff check .` 与 `pytest`，在 `minerva-ui` 执行 `npm run build` 作基本校验。  
3. 通过 Pull Request 合并。
