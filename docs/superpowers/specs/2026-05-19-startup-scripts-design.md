# 服务启动脚本与多环境配置设计

**日期**：2026-05-19  
**状态**：已实现（2026-05-19）  
**依据**：头脑风暴——将 FastAPI 主服务与 Celery Worker/Beat 拆分为独立启动脚本（Windows + Linux）；环境配置改为「单 profile → 单 `.env.<profile>` 文件」，无叠加；`run-backend` 无参默认 `local`；`run-celery` 必须显式 `<profile> <worker|beat>`，不支持 `both`。

---

## 1. 背景与目标

### 1.1 现状

- `scripts/run-backend.cmd` / `run-backend.sh` 在同一脚本内启动 **uvicorn + Celery Worker + Beat**。
- `backend/app/config.py` 加载 **`.env.dev` + `.env.dev.<APP_ENV>`** 两层合并；未设 `APP_ENV` 时默认从 `.env.dev` 推断为 `dev`。
- 可选环境变量 `MINERVA_SKIP_CELERY_WORKER` / `MINERVA_SKIP_CELERY_BEAT` 用于跳过 Celery。

### 1.2 目标

1. **脚本拆分**：`run-backend` 仅启动 FastAPI；`run-celery` 启动 Celery（`worker` 或 `beat` 二选一）。
2. **跨平台**：Windows（`.cmd`）与 Linux/macOS（`.sh`）成对维护；共享 `_backend-common.*` 减少重复。
3. **多环境**：profile 与 `backend/.env.<profile>` 一对一；**不叠加**任何 env 文件。
4. **默认本地**：`run-backend` 无参 → `APP_ENV=local` → `.env.local`。
5. **Celery 严格 CLI**：`run-celery <profile> <worker|beat>`，参数个数或子命令不合法则报错并打印用法；**无 `both`**；需同时跑 Worker 与 Beat 时执行两次命令。

### 1.3 成功标准

- 开发者可用两条命令分别启动 API 与 Celery，且 Win/Linux 行为与本文一致。
- `APP_ENV=dev` 时仅读取 `.env.dev`，不读取 `.env.local`。
- README、`.env.example`、`minerva-conventions` 与实现一致；`run-backend` 中无 Celery 代码、无 `MINERVA_SKIP_CELERY_*`。

---

## 2. 范围与边界

### 2.1 本次范围

| 项 | 说明 |
|----|------|
| `scripts/run-backend.cmd` / `.sh` | 仅 uvicorn；可选 `[profile]` |
| `scripts/run-celery.cmd` / `.sh` | 新建；`<profile> <worker\|beat>` |
| `scripts/_backend-common.cmd` / `.sh` | 新建；Python 解析、env 校验、`APP_ENV` |
| `backend/app/config.py` | 单文件加载；默认 profile `local` |
| `backend/.env.example` | 头注释更新 |
| `README.md` / `README.en.md` | 启动说明更新 |
| `.cursor/skills/minerva-conventions/SKILL.md` | §3 加载顺序与脚本列表 |

### 2.2 非本次范围

- Docker / systemd / CI 编排（可后续复用同一 `APP_ENV` 约定）。
- 新增 `prod` / `staging` 的 env 文件内容（仅约定命名，由运维自建）。
- 前端 `run-frontend` 脚本逻辑变更（仅注释可指向新后端启动方式）。
- Celery 任务实现、`celery_app.py` 行为变更。

---

## 3. CLI 与脚本行为

### 3.1 `run-backend`

```
run-backend[.cmd|.sh] [profile]
```

| 调用 | `APP_ENV` | 加载文件 |
|------|-----------|----------|
| 无参 | `local` | `backend/.env.local` |
| `dev` | `dev` | `backend/.env.dev` |
| `<name>` | `<name>` | `backend/.env.<name>` |

进程：`uvicorn app.main:app --reload --host 0.0.0.0 --port ${MINERVA_BACKEND_PORT:-8000}`

### 3.2 `run-celery`

```
run-celery[.cmd|.sh] <profile> <worker|beat>
```

- **必须恰好 2 个参数**；否则打印用法并 `exit 1`。
- 第二参数仅允许 `worker` 或 `beat`；**不支持 `both`**。
- 同时需要 Worker 与 Beat：开两个终端（或 Windows 下执行两次，各开一个 `cmd /k` 窗口）：
  - `run-celery.cmd local worker`
  - `run-celery.cmd local beat`

| 平台 | 行为 |
|------|------|
| Windows | 每次调用 `start "Minerva Celery Worker|Beat" cmd /k "..."` 打开独立窗口后退出 |
| Linux | 当前终端前台运行对应 `celery` 子进程 |

Celery 命令（与现有一致）：

- Worker: `python -m celery -A app.celery_app:celery_app worker --loglevel=INFO`
- Beat: `python -m celery -A app.celery_app:celery_app beat --loglevel=INFO`

### 3.3 共享模块 `_backend-common`

职责：

1. 解析仓库根、`backend/` 目录。
2. 解析 Python（顺序与现 `run-backend.cmd` 一致：venv → `py -3.13/3.12/3.11` → `python`）。
3. 根据 profile 设置 `APP_ENV` 并 `export`/`set`。
4. 校验 `backend/.env.<profile>` 存在；不存在则 stderr 提示并 `exit 1`。
5. `cd` 至 `backend/`。

`run-celery` 在调用 common 前/后解析第二参数为 `worker` 或 `beat`。

### 3.4 用法输出（stderr）

**run-backend**

```
用法: run-backend[.cmd|.sh] [profile]
  profile  环境名，对应 backend/.env.<profile>（默认 local）

示例:
  run-backend.cmd
  run-backend.cmd dev
```

**run-celery**

```
用法: run-celery[.cmd|.sh] <profile> <worker|beat>
  profile  环境名，对应 backend/.env.<profile>
  子命令   worker 或 beat（须同时跑两者时请各执行一次）

示例:
  run-celery.cmd local worker
  run-celery.cmd local beat
  run-celery.cmd dev worker
```

### 3.5 删除项

- `run-backend` 内所有 Celery `start` / 后台进程逻辑。
- 环境变量 `MINERVA_SKIP_CELERY_WORKER`、`MINERVA_SKIP_CELERY_BEAT` 及文档引用。

---

## 4. 配置加载（`config.py`）

### 4.1 规则

```
优先级（高 → 低）：
  1. 进程环境变量（shell / 脚本 / IDE / CI）
  2. 单个 dotenv：backend/.env.<APP_ENV>
  3. Settings 字段代码默认值
```

- **废弃**：`.env.dev` + `.env.dev.<APP_ENV>` 叠加；仓库内若有 `.env.dev.local` 等旧文件不再被自动加载，迁移为独立 `.env.<profile>`。

### 4.2 `_discover_app_env()`

- `os.environ["APP_ENV"]` 非空 → 使用该值。
- 否则 → **`local`**（不再读 `.env.dev` 内 `APP_ENV` 行）。

### 4.3 `_env_file_paths()`

```python
app_env = _discover_app_env()
path = _BACKEND_DIR / f".env.{app_env}"
return (str(path),) if path.is_file() else None
```

### 4.4 环境文件约定

| 文件 | 用途 |
|------|------|
| `backend/.env.example` | 模板（入库） |
| `backend/.env.local` | 默认本地（`run-backend` 无参） |
| `backend/.env.dev` | 团队/远程 dev（`run-backend dev`） |
| `backend/.env.<profile>` | 其它环境按需自建 |

首次使用：`cp backend/.env.example backend/.env.local` 后按需修改。

### 4.5 非脚本启动（IDE / pytest）

- 未设置 `APP_ENV` 时默认 `local`，尝试加载 `.env.local`。
- 文件缺失时回退到代码默认值；建议在 IDE Run Configuration 中设置 `APP_ENV` 或保证 `.env.local` 存在。

### 4.6 `Settings.app_env` 字段

更新 `description`：说明 profile 与 `.env.<profile>` 单文件对应关系；启动脚本在调用 Python 前设置 `APP_ENV`。

**`APP_ENV` 对 CORS / bootstrap 的语义不变**（`dev` / `development` / `local` / `test` 等仍按现有 `main.py`、`bootstrap.py` 判断）。

---

## 5. 保留的环境变量

| 变量 | 使用者 | 说明 |
|------|--------|------|
| `APP_ENV` | 脚本 → `config.py` | profile 名，决定 `.env.<profile>` |
| `MINERVA_BACKEND_PORT` | `run-backend` | 默认 `8000` |
| `MINERVA_CELERY_USE_PREFORK` | Celery（现有） | Windows prefork 可选，文档保留在 `run-celery` 注释 |

---

## 6. 错误处理

| 场景 | 行为 |
|------|------|
| `.env.<profile>` 不存在 | 报错，提示 `cp .env.example .env.<profile>`，`exit 1` |
| `run-celery` 参数 ≠ 2 | 用法 + `exit 1` |
| 子命令非 `worker`/`beat` | 用法 + `exit 1` |
| 找不到 Python | 与现脚本相同提示 |

---

## 7. 文档同步清单

- [x] `backend/.env.example` 头部注释
- [x] `README.md` / `README.en.md` 启动章节（`run-backend` + `run-celery`、`.env.local`）
- [x] `.cursor/skills/minerva-conventions/SKILL.md` §3
- [x] `scripts/run-frontend.*` 注释（可选，指向 `run-backend`）

---

## 8. 验收清单

1. Windows：`run-backend.cmd` 仅 uvicorn；`run-celery.cmd local worker` / `local beat` 各开独立窗口。
2. Linux：`bash scripts/run-backend.sh` 仅 uvicorn；`bash scripts/run-celery.sh local worker` 前台 worker。
3. `APP_ENV=dev` 且存在 `.env.dev` 时，`settings.database_url` 来自 `.env.dev`，不混入 `.env.local`。
4. `run-backend` 无 Celery 代码；grep 无 `MINERVA_SKIP_CELERY`。
5. README 与 `.env.example` 描述与 §4 一致。

---

## 9. 实现对照（以代码为准，2026-05-19）

| spec 条目 | 代码位置 | 状态 |
|-----------|----------|------|
| `run-backend` 仅 uvicorn | `scripts/run-backend.cmd`, `scripts/run-backend.sh` | 已实现 |
| `run-celery` 严格两参数 | `scripts/run-celery.cmd`, `scripts/run-celery.sh` | 已实现 |
| `_backend-common` | `scripts/_backend-common.cmd`, `scripts/_backend-common.sh` | 已实现 |
| 单文件 env 加载 | `backend/app/config.py`, `backend/tests/test_config_env_loading.py` | 已实现 |
| 文档同步 | `README.md`, `README.en.md`, `backend/.env.example`, `minerva-conventions` | 已实现 |
