# Windows Celery Worker 可靠性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 开发机上稳定运行 Celery Worker（消费 `sys_celery` 定时任务与 run-now），并改善 Broker 断连恢复与进程退出体验。

**Architecture:** Windows 默认 `threads` pool（可 env 回退 `solo`/`prefork`）；`celery_app.conf` 增加 broker 心跳与断连取消长任务；启动脚本显式传 `--pool`/`--concurrency`；新增 `stop-celery` 脚本结束进程树。验证以 spec §9 手工清单为准（项目已移除 pytest）。

**Tech Stack:** Python 3.11+, Celery 5, Redis/Kombu, Windows cmd/bash 启动脚本。

**Spec:** `docs/superpowers/specs/2026-05-22-windows-celery-reliability-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/config.py` | `celery_worker_pool`、`celery_worker_concurrency`（env 别名） |
| `backend/app/celery_app.py` | 解析 pool、设置 `worker_pool`/broker 可靠性 conf |
| `backend/.env.example` / `.env.dev` | 新变量注释与默认值 |
| `scripts/run-celery.cmd` / `.sh` | Worker 传 pool/concurrency |
| `scripts/stop-celery.cmd` / `.sh` | 强制结束 Celery 进程树 |
| `README.md` / `README.en.md` | Windows 排错、双终端、WSL 可选 |
| `.cursor/skills/minerva-conventions/SKILL.md` | §3 脚本与 env 列表 |
| `docs/superpowers/specs/2026-05-22-windows-celery-reliability-design.md` | §10 实现对照回填 |

---

### Task 1: Settings 与 env 模板

**Files:**
- Modify: `backend/app/config.py`（`celery_broker_connection_max_retries` 字段之后）
- Modify: `backend/.env.example`（脚本专用区）
- Modify: `backend/.env.dev`（若需与 example 对齐）

- [ ] **Step 1: 在 `config.py` 增加字段**

在 `Settings` 类中、`celery_broker_connection_max_retries` 之后追加：

```python
    celery_worker_pool: str | None = Field(
        default=None,
        description=(
            "Celery worker pool override (threads|solo|prefork). "
            "Empty uses platform default in celery_app (Windows: threads)."
        ),
        validation_alias=AliasChoices(
            "MINERVA_CELERY_POOL",
            "CELERY_WORKER_POOL",
            "celery_worker_pool",
        ),
    )
    celery_worker_concurrency: int = Field(
        default=4,
        ge=1,
        le=64,
        description="Worker concurrency when pool is threads or prefork.",
        validation_alias=AliasChoices(
            "MINERVA_CELERY_CONCURRENCY",
            "CELERY_WORKER_CONCURRENCY",
            "celery_worker_concurrency",
        ),
    )
```

- [ ] **Step 2: 更新 `backend/.env.example` 脚本区**

删除错误行：

```env
# app/celery_app.py：Windows 上强制使用 prefork 池（默认 threads）
# MINERVA_CELERY_USE_PREFORK=1
```

替换为：

```env
# scripts/run-celery.*：Worker 池（Windows 默认 threads；Linux 默认 prefork）
# MINERVA_CELERY_POOL=threads
# MINERVA_CELERY_CONCURRENCY=4
# 兼容旧开关：MINERVA_CELERY_USE_PREFORK=1 等价于 prefork
```

- [ ] **Step 3: 同步 `backend/.env.dev`**

在「脚本/测试专用」注释块加入与 example 相同的三行（可不取消注释，保持默认即可）。

- [ ] **Step 4: 验证 Settings 加载**

Run:

```bat
cd backend
set APP_ENV=dev
python -c "from app.config import settings; print(settings.celery_worker_pool, settings.celery_worker_concurrency)"
```

Expected: `None 4`（未设 `MINERVA_CELERY_POOL` 时 pool 为 None）。

- [ ] **Step 5: Commit**

```bat
git add backend/app/config.py backend/.env.example backend/.env.dev
git commit -m "feat(celery): add worker pool and concurrency settings"
```

---

### Task 2: `celery_app.py` pool 解析与 Broker 可靠性

**Files:**
- Modify: `backend/app/celery_app.py`

- [ ] **Step 1: 增加 pool 解析函数（模块级，` _build_celery_app` 之前）**

```python
_VALID_CELERY_POOLS = frozenset({"solo", "threads", "prefork"})


def resolve_worker_pool_name() -> str:
    """Return effective Celery worker pool for this process.

    Priority: ``MINERVA_CELERY_USE_PREFORK`` (legacy) > ``settings.celery_worker_pool`` /
    ``MINERVA_CELERY_POOL`` > platform default (Windows: threads, else prefork).
    """

    legacy_prefork = os.getenv("MINERVA_CELERY_USE_PREFORK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if legacy_prefork:
        return "prefork"
    raw = (settings.celery_worker_pool or os.getenv("MINERVA_CELERY_POOL", "") or "").strip().lower()
    if raw in _VALID_CELERY_POOLS:
        return raw
    if sys.platform == "win32":
        return "threads"
    return "prefork"


def resolve_worker_concurrency() -> int:
    """Clamp configured worker concurrency to [1, 64]."""

    return max(1, min(64, int(settings.celery_worker_concurrency)))
```

- [ ] **Step 2: 在 `celery_app.conf.update(...)` 内追加可靠性键**

在现有 `redis_backend_health_check_interval=...` 之后、`)` 之前增加：

```python
        broker_heartbeat=30,
        worker_cancel_long_running_tasks_on_connection_loss=True,
```

- [ ] **Step 3: 替换 Windows solo 块**

删除 `_win_prefork` 与 `if sys.platform == "win32" and not _win_prefork: celery_app.conf.worker_pool = "solo"`，改为：

```python
    pool_name = resolve_worker_pool_name()
    celery_app.conf.worker_pool = pool_name
    if pool_name in ("threads", "prefork"):
        celery_app.conf.worker_concurrency = resolve_worker_concurrency()
```

- [ ] **Step 4: 更新模块 docstring**

将「defaults worker_pool to solo」改为「defaults worker_pool to threads on Windows unless overridden」。

- [ ] **Step 5: 更新 `worker_process_init` 注释**

注明补丁仅在 `prefork` 时有意义；逻辑保持不变。

- [ ] **Step 6: 冒烟导入**

Run:

```bat
cd backend
set APP_ENV=dev
python -c "from app.celery_app import celery_app, resolve_worker_pool_name; print(resolve_worker_pool_name(), celery_app.conf.worker_pool if celery_app else None)"
```

Expected（Windows）: `threads threads`

- [ ] **Step 7: Commit**

```bat
git add backend/app/celery_app.py
git commit -m "feat(celery): default Windows worker pool to threads and harden broker"
```

---

### Task 3: `run-celery` 启动脚本

**Files:**
- Modify: `scripts/run-celery.cmd`
- Modify: `scripts/run-celery.sh`

- [ ] **Step 1: 修改 `run-celery.cmd`**

在 `set CELERY_APP=...` 之后、`broker_preflight` 之前增加（从环境读取，默认 threads / 4）：

```bat
if not defined MINERVA_CELERY_POOL set "MINERVA_CELERY_POOL=threads"
if not defined MINERVA_CELERY_CONCURRENCY set "MINERVA_CELERY_CONCURRENCY=4"
```

将最后一行 celery 调用按子命令分支：

```bat
if /i "%SUBCMD%"=="worker" (
  "%MINERVA_PYTHON%" -m celery -A %CELERY_APP% worker --loglevel=INFO --pool=%MINERVA_CELERY_POOL% --concurrency=%MINERVA_CELERY_CONCURRENCY%
) else (
  "%MINERVA_PYTHON%" -m celery -A %CELERY_APP% beat --loglevel=INFO
)
```

更新文件头 REM：说明 Windows 推荐 `threads`；`MINERVA_CELERY_USE_PREFORK=1` 等价 `MINERVA_CELERY_POOL=prefork`。

- [ ] **Step 2: 修改 `run-celery.sh`**

在 `minerva_backend_setup` 之后：

```bash
export MINERVA_CELERY_POOL="${MINERVA_CELERY_POOL:-}"
export MINERVA_CELERY_CONCURRENCY="${MINERVA_CELERY_CONCURRENCY:-4}"
if [[ "${SUBCMD}" == "worker" ]]; then
  POOL="${MINERVA_CELERY_POOL}"
  if [[ -z "${POOL}" ]]; then
    if [[ "$(uname -s 2>/dev/null || true)" == *MINGW* ]] || [[ "$(uname -s 2>/dev/null || true)" == *MSYS* ]]; then
      POOL="threads"
    else
      POOL="prefork"
    fi
  fi
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" worker --loglevel=INFO \
    --pool="${POOL}" --concurrency="${MINERVA_CELERY_CONCURRENCY}"
else
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" beat --loglevel=INFO
fi
```

（删除原有单行 `worker`/`beat` exec。）

- [ ] **Step 3: 手工启动 Worker 看 banner**

Run（仓库根目录）：

```bat
scripts\run-celery.cmd local worker
```

Expected：日志含 `concurrency: 4` 与 `pool: threads`（或 `Pool: threads`），随后 `ready`。

Ctrl+C 试退出；若无效记为 Task 4 验证项。

- [ ] **Step 4: Commit**

```bat
git add scripts/run-celery.cmd scripts/run-celery.sh
git commit -m "feat(scripts): pass Celery pool and concurrency in run-celery"
```

---

### Task 4: `stop-celery` 脚本

**Files:**
- Create: `scripts/stop-celery.cmd`
- Create: `scripts/stop-celery.sh`

- [ ] **Step 1: 创建 `scripts/stop-celery.cmd`**

```bat
@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM 结束本机 Minerva Celery Worker/Beat 进程（Ctrl+C 无效时使用）。

echo 正在结束 Celery 相关进程...
taskkill /F /T /FI "IMAGENAME eq celery.exe" 2>nul
if errorlevel 1 (
  echo 未发现 celery.exe 进程。
) else (
  echo 已发送 taskkill 至 celery.exe 进程树。
)

for /f "tokens=1" %%p in ('wmic process where "CommandLine like '%%celery -A app.celery_app%%'" get ProcessId 2^>nul ^| findstr /r "[0-9]"') do (
  taskkill /F /PID %%p 2>nul
)

echo 完成。若仍有残留，请在任务管理器中结束对应 python.exe。
exit /b 0
```

- [ ] **Step 2: 创建 `scripts/stop-celery.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "Stopping Celery processes matching app.celery_app..."
pkill -f "celery -A app.celery_app" 2>/dev/null || true
echo "Done."
```

- [ ] **Step 3: 赋予 sh 可执行（Git Bash / Linux）**

```bash
chmod +x scripts/stop-celery.sh
```

- [ ] **Step 4: 验证 stop（先启动 worker 再执行）**

```bat
scripts\stop-celery.cmd
tasklist | findstr /i celery
```

Expected: 无 `celery.exe` 行（或仅剩无关进程）。

- [ ] **Step 5: Commit**

```bat
git add scripts/stop-celery.cmd scripts/stop-celery.sh
git commit -m "feat(scripts): add stop-celery to kill worker/beat on Windows"
```

---

### Task 5: README 与 minerva-conventions

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `.cursor/skills/minerva-conventions/SKILL.md`

- [ ] **Step 1: 在 README「启动服务」Celery 小节追加「Windows Celery 排错」**

中文要点（插入 `run-celery` 示例之后）：

- 必须 **Worker + Beat 两个终端**。
- Windows 默认 **`threads` 池**（`MINERVA_CELERY_POOL` / `MINERVA_CELERY_CONCURRENCY`）。
- 假死不消费：查 Redis `LLEN celery`、Beat 是否 `Sending due task`、Worker 是否 `received`；清锁 `minerva:celery:scheduled_singleton:*`。
- **Ctrl+C 无效** → `scripts\stop-celery.cmd`。
- 可选：WSL2/Docker 跑 `run-celery.sh`。

- [ ] **Step 2: 同步 `README.en.md` 英文版**

- [ ] **Step 3: 更新 `minerva-conventions` §3**

在「启动脚本约定」列举：`run-celery.*`、`stop-celery.*`；环境变量表增加 `MINERVA_CELERY_POOL`、`MINERVA_CELERY_CONCURRENCY`、`MINERVA_CELERY_USE_PREFORK`（兼容）。

- [ ] **Step 4: Commit**

```bat
git add README.md README.en.md .cursor/skills/minerva-conventions/SKILL.md
git commit -m "docs: Windows Celery troubleshooting and pool env vars"
```

---

### Task 6: 回填 design spec §10

**Files:**
- Modify: `docs/superpowers/specs/2026-05-22-windows-celery-reliability-design.md`

- [ ] **Step 1: 将 §10 表格状态改为「已实现」并注明提交范围**

- [ ] **Step 2: 在 §11 修订记录增加一行「2026-05-22 按 plan 实现」**

- [ ] **Step 3: Commit**

```bat
git add docs/superpowers/specs/2026-05-22-windows-celery-reliability-design.md
git commit -m "docs: mark Windows Celery reliability spec as implemented"
```

---

### Task 7: 手工验收（spec §9）

- [ ] **Step 1: 基线 30 分钟**

配置 `sys_celery` → `demo.default_job`、Cron `*/1 * * * *`；开 Beat + Worker（threads）。30 分钟内每分钟有 `demo.default_job start`。

- [ ] **Step 2: run-now**

设置页「立即执行」应在数秒内出现 Worker `received`。

- [ ] **Step 3: 断 Redis（可选）**

停 Redis 30s 后重启；观察 Worker 是否恢复消费或按 README 重启一次即可。

- [ ] **Step 4: 退出**

`stop-celery.cmd` 10 秒内清进程；对比 Ctrl+C 行为记入 README 若仍不可靠。

- [ ] **Step 5: 回退 solo**

`set MINERVA_CELERY_POOL=solo` 后重启 Worker，确认文档所述串行行为仍可复现旧问题场景（用于对比，非回归失败）。

---

## Spec coverage checklist

| Spec § | Task |
|--------|------|
| §5.1 threads 默认 + env | Task 1–2 |
| §5.2 broker heartbeat / cancel on loss | Task 2 |
| §5.3 单例锁运维说明 | Task 5 |
| §6.1 run-celery CLI | Task 3 |
| §6.2 stop-celery.cmd | Task 4 |
| §6.3 run-celery.sh + stop-celery.sh | Task 3–4 |
| §7 README 排错 + WSL 可选 | Task 5 |
| §8 env/conventions | Task 1, 5 |
| §9 手工验证 | Task 7 |
| §10 对照表 | Task 6 |

---

## Plan self-review notes

- 无 TBD 步骤；测试改为手工清单（与 spec「不恢复 pytest」一致）。
- `resolve_worker_pool_name` 与脚本默认在 Windows 均为 `threads`，一致。
- Linux 未设 env 时脚本传 `prefork`，与 Celery CLI 默认一致；`celery_app` 在非 Windows 默认 `prefork` 与 conf 对齐。
