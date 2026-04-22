# Minerva

文档智能与规则流编排：FastAPI 后端、React 前端、PostgreSQL + Redis。本地开发建议用 Docker 提供数据库与缓存。

## 环境要求

| 依赖 | 说明 |
|------|------|
| Docker | 用于 `docker compose` 启动 PostgreSQL 与 Redis |
| Python | 3.11+ |
| Node.js | 20+ |
| 系统 | 已开放端口 5432、6379、8000、5173 供本机访问 |

## 一、拉代码与基础设施

1. 克隆本仓库，在**仓库根目录**执行，启动数据库与缓存：

   ```bash
   docker compose up -d
   ```

2. 确认容器运行正常（`postgres` 与 `redis` 均为 Up）。

## 二、配置环境变量

在仓库**根目录**有 `.env.example`，请复制为后端的 `backend/.env`：

**Linux / macOS：**

```bash
cp .env.example backend/.env
```

**Windows (PowerShell)：**

```powershell
Copy-Item .env.example backend/.env
```

`backend/.env` 中默认同目录示例即可连接本机 `docker compose` 暴露的库与 Redis（`127.0.0.1:5432` / `127.0.0.1:6379`）。**生产或多人协作时请修改 `JWT_SECRET` 为足够长的随机串。**

## 三、启动后端

在 **`backend` 目录** 下操作：

```bash
cd backend
```

1. 创建虚拟环境（可选，推荐）后安装依赖与可编辑安装：

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   # Linux/macOS: source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. 执行数据库迁移，使表结构与当前代码一致：

   ```bash
   alembic upgrade head
   ```

3. 启动 API 服务（热重载）：

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

成功后可访问接口文档： [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) ，健康检查： [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz) 。

**说明：**

- 后端会读取 `backend/.env` 中的 `DATABASE_URL`、`SYNC_DATABASE_URL`（Alembic 使用同步 URL）、`REDIS_URL`、JWT 等配置。
- 与前端联调时，CORS 已允许 `http://localhost:5173` 与 `http://127.0.0.1:5173` 。

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

4. 浏览器打开终端中提示的地址（默认多为 [http://127.0.0.1:5173](http://127.0.0.1:5173) ），在页面中**注册/登录**后即可使用规则、设计器、执行等模块。

5. 生产构建立：

   ```bash
   npm run build
   ```

   输出在 `minerva-ui/dist/`，可交由任意静态资源服务器或反向代理到后端。

## 五、（可选）启动执行 Worker

规则「运行」、执行入队后，需 **Redis 可达**，并单独启动 ARQ Worker 以消费任务、步进执行：

```bash
cd backend
# 已激活同一虚拟环境
arq app.worker.arq.WorkerSettings
```

若本机 `REDIS_URL` 无法连接，Worker 会启动失败；仅调试 API 与 UI 时可在未启动 Worker 的情况下使用其他功能，但**执行**相关行为可能一直为排队或需自行排查。

## 六、服务与地址一览

| 服务 | 默认地址 | 说明 |
|------|----------|------|
| 前端 (Vite) | http://127.0.0.1:5173 | 见 `minerva-ui` 的 `npm run dev` 输出 |
| 后端 API | http://127.0.0.1:8000 | FastAPI，Swagger 见 `/docs` |
| PostgreSQL | 127.0.0.1:5432 | 用户/库/密码与 `docker-compose.yml` 一致时可用 `.env.example` 默认连接串 |
| Redis | 127.0.0.1:6379 | Worker 与部分执行逻辑依赖 |

## 使用说明（简要）

- 登录/注册 调用 `POST /auth/login`、`/auth/register`；当前工作空间 ID 在 JWT 的 `wid` 声明中，前端会据此请求 `/workspaces/{id}/...`。
- 规则**运行**前需在界面将规则**发布**（存在已发布版本）。
- 更详细的开发约定与任务列表见 `docs/superpowers/plans/` 下实现计划与规格说明。

## 参与贡献

1. Fork 本仓库并新建功能分支。  
2. 提交前建议在后端目录执行 `ruff check .` 与 `pytest`，在 `minerva-ui` 执行 `npm run build` 作基本校验。  
3. 通过 Pull Request 合并。
