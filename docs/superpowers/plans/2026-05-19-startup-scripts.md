# 服务启动脚本与多环境配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 FastAPI 与 Celery 拆为独立跨平台启动脚本，并将 `config.py` 改为按 `APP_ENV` 只加载单个 `backend/.env.<profile>` 文件（默认 `local`）。

**Architecture:** 新增 `scripts/_backend-common.{sh,cmd}` 统一解析 Python、设置 `APP_ENV`、校验 env 文件；`run-backend` 仅 uvicorn；`run-celery` 严格 `<profile> <worker|beat>`。`config.py` 的 `_discover_app_env` 默认 `local`，`_env_file_paths` 只返回 `.env.<profile>`。

**Tech Stack:** Bash, Windows cmd, Pydantic Settings, uvicorn, Celery, pytest

**Spec:** `docs/superpowers/specs/2026-05-19-startup-scripts-design.md`

---

## File map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/config.py` | Modify | 单文件 dotenv；默认 profile `local` |
| `backend/tests/test_config_env_loading.py` | Create | `_discover_app_env` / `_env_file_paths` 单元测试 |
| `scripts/_backend-common.sh` | Create | Bash：Python、profile、env 校验 |
| `scripts/_backend-common.cmd` | Create | Windows：同上 |
| `scripts/run-backend.sh` | Modify | 去掉 Celery；调用 common |
| `scripts/run-backend.cmd` | Modify | 去掉 Celery；调用 common |
| `scripts/run-celery.sh` | Create | `<profile> <worker\|beat>` |
| `scripts/run-celery.cmd` | Create | 同上 + 独立窗口 |
| `backend/.env.example` | Modify | 头注释 |
| `README.md` / `README.en.md` | Modify | 启动说明 |
| `.cursor/skills/minerva-conventions/SKILL.md` | Modify | §3 加载顺序、脚本列表 |
| `scripts/run-frontend.sh` / `.cmd` | Modify | 注释（可选） |
| `docs/superpowers/specs/2026-05-19-startup-scripts-design.md` | Modify | §9 实现对照、状态 |

---

### Task 1: `config.py` 单文件加载

**Files:**
- Modify: `backend/app/config.py`（`_discover_app_env`、`_env_file_paths`、`Settings.app_env` description）
- Create: `backend/tests/test_config_env_loading.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_config_env_loading.py
"""Unit tests for single-profile dotenv discovery in app.config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app import config as config_module

_BACKEND_DIR = Path(config_module._BACKEND_DIR)


def test_discover_app_env_defaults_to_local_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When APP_ENV is not in the process environment, default profile is local."""
    monkeypatch.delenv("APP_ENV", raising=False)
    assert config_module._discover_app_env() == "local"


def test_discover_app_env_uses_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Process APP_ENV overrides the default."""
    monkeypatch.setenv("APP_ENV", "dev")
    assert config_module._discover_app_env() == "dev"


def test_env_file_paths_returns_single_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only backend/.env.<profile> is returned when the file exists."""
    env_file = tmp_path / ".env.staging"
    env_file.write_text("APP_NAME=staging-test\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "staging")
    paths = config_module._env_file_paths()
    assert paths == (str(env_file),)


def test_env_file_paths_returns_none_when_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing dotenv file yields None so Settings falls back to code defaults."""
    monkeypatch.setattr(config_module, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "missing")
    assert config_module._env_file_paths() is None


def test_env_file_paths_does_not_layer_dev_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Legacy .env.dev + .env.dev.local must not both be loaded."""
    (tmp_path / ".env.dev").write_text("APP_NAME=from-dev\n", encoding="utf-8")
    (tmp_path / ".env.dev.local").write_text("APP_NAME=from-overlay\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "dev")
    paths = config_module._env_file_paths()
    assert paths == (str(tmp_path / ".env.dev"),)
    assert len(paths) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_config_env_loading.py -v`

Expected: FAIL — `test_env_file_paths_does_not_layer_dev_files` 因当前仍返回两个路径，或 `test_discover_app_env_defaults_to_local_when_unset` 得到 `dev`

- [ ] **Step 3: 修改 `config.py`**

将 `_discover_app_env` 替换为：

```python
def _discover_app_env() -> str:
    """APP_ENV: 进程环境变量优先；未设置时默认 local（对应 .env.local）。"""
    v = os.environ.get("APP_ENV", "").strip()
    return v or "local"
```

将 `_env_file_paths` 替换为：

```python
def _env_file_paths() -> tuple[str, ...] | None:
    """单环境：仅加载 backend/.env.<APP_ENV>（文件存在才加载）。"""
    app_env = _discover_app_env()
    path = _BACKEND_DIR / f".env.{app_env}"
    return (str(path),) if path.is_file() else None
```

更新 `Settings.app_env` 的 `description`：

```python
    app_env: str = Field(
        default=_APP_ENV,
        description=(
            "运行环境 profile 名。启动脚本在调用 Python 前设置 APP_ENV；"
            "仅加载 backend/.env.<profile> 单个文件（无叠加）。"
        ),
        validation_alias=AliasChoices("APP_ENV", "app_env"),
    )
```

更新模块顶部 docstring 一行：`"""Application settings: env vars, single dotenv file per profile, typed defaults."""`

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_config_env_loading.py -v`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config_env_loading.py
git commit -m "refactor(config): load single .env.<profile> file, default local"
```

---

### Task 2: Bash 共享模块与 `run-backend` / `run-celery`

**Files:**
- Create: `scripts/_backend-common.sh`
- Modify: `scripts/run-backend.sh`
- Create: `scripts/run-celery.sh`

- [ ] **Step 1: 创建 `scripts/_backend-common.sh`**

```bash
#!/usr/bin/env bash
# 被 run-backend.sh / run-celery.sh source；勿直接执行。
# 用法: minerva_backend_setup <profile>
# 设置: MINERVA_BACKEND_DIR, MINERVA_PYTHON, APP_ENV；失败时 exit 1

minerva_backend_setup() {
  local profile="${1:?profile required}"
  local script_dir repo_root backend_dir env_file

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "${script_dir}/.." && pwd)"
  backend_dir="${repo_root}/backend"
  env_file="${backend_dir}/.env.${profile}"

  export APP_ENV="${profile}"
  export MINERVA_BACKEND_DIR="${backend_dir}"

  if [[ ! -f "${env_file}" ]]; then
    echo "错误: 未找到环境文件 ${env_file}" >&2
    echo "提示: cp backend/.env.example backend/.env.${profile}" >&2
    exit 1
  fi

  if [[ -f "${backend_dir}/.venv/bin/python" ]]; then
    MINERVA_PYTHON="${backend_dir}/.venv/bin/python"
  elif [[ -f "${backend_dir}/minerva/Scripts/python.exe" ]]; then
    MINERVA_PYTHON="${backend_dir}/minerva/Scripts/python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    MINERVA_PYTHON="python3"
  elif command -v python >/dev/null 2>&1; then
    MINERVA_PYTHON="python"
  else
    echo "错误: 未找到 python3 或 python，请安装 Python 3.11+ 或在 backend/.venv 创建虚拟环境。" >&2
    exit 1
  fi
  export MINERVA_PYTHON

  cd "${backend_dir}" || exit 1
  echo "环境: APP_ENV=${APP_ENV}  文件: ${env_file}"
  echo "Python: ${MINERVA_PYTHON}"
}
```

- [ ] **Step 2: 重写 `scripts/run-backend.sh`**

```bash
#!/usr/bin/env bash
# 启动 FastAPI（仅 uvicorn）。用法: run-backend.sh [profile]  默认 profile=local
# 环境变量: MINERVA_BACKEND_PORT（默认 8000）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"

PROFILE="${1:-local}"
PORT="${MINERVA_BACKEND_PORT:-8000}"

minerva_backend_setup "${PROFILE}"

echo "目录: ${MINERVA_BACKEND_DIR}  端口: ${PORT}"
exec "${MINERVA_PYTHON}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT}"
```

- [ ] **Step 3: 创建 `scripts/run-celery.sh`**

```bash
#!/usr/bin/env bash
# 启动 Celery Worker 或 Beat。用法: run-celery.sh <profile> <worker|beat>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"

usage() {
  cat >&2 <<'EOF'
用法: run-celery.sh <profile> <worker|beat>
  profile  环境名，对应 backend/.env.<profile>
  子命令   worker 或 beat（须同时跑两者时请各执行一次）

示例:
  run-celery.sh local worker
  run-celery.sh local beat
  run-celery.sh dev worker
EOF
}

if [[ $# -ne 2 ]]; then
  usage
  exit 1
fi

PROFILE="$1"
SUBCMD="$2"

case "${SUBCMD}" in
  worker|beat) ;;
  *)
    echo "错误: 子命令必须是 worker 或 beat，收到: ${SUBCMD}" >&2
    usage
    exit 1
    ;;
esac

minerva_backend_setup "${PROFILE}"

CELERY_APP="app.celery_app:celery_app"
if [[ "${SUBCMD}" == "worker" ]]; then
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" worker --loglevel=INFO
else
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" beat --loglevel=INFO
fi
```

- [ ] **Step 4: 赋予可执行权限（Linux/macOS）**

Run: `chmod +x scripts/_backend-common.sh scripts/run-backend.sh scripts/run-celery.sh`

- [ ] **Step 5: 手动冒烟（可选，有 `.env.local` 时）**

Run: `bash scripts/run-celery.sh`  
Expected: 用法说明 + exit 1

Run: `APP_ENV=local bash -c 'source scripts/_backend-common.sh && minerva_backend_setup local && cd backend && python -c "import os; print(os.environ.get(\"APP_ENV\"))"'`  
Expected: 打印 `local`（若 `.env.local` 存在）

- [ ] **Step 6: Commit**

```bash
git add scripts/_backend-common.sh scripts/run-backend.sh scripts/run-celery.sh
git commit -m "feat(scripts): split celery to run-celery.sh, shared bash common"
```

---

### Task 3: Windows `cmd` 脚本

**Files:**
- Create: `scripts/_backend-common.cmd`
- Modify: `scripts/run-backend.cmd`
- Create: `scripts/run-celery.cmd`

- [ ] **Step 1: 创建 `scripts/_backend-common.cmd`**

```bat
@echo off
REM 由 run-backend.cmd / run-celery.cmd 调用: call _backend-common.cmd <profile>
REM 设置 APP_ENV、MINERVA_BACKEND_DIR；解析 MINERVA_PYTHON 到调用方可见变量
setlocal EnableExtensions

set "MINERVA_PROFILE=%~1"
if not defined MINERVA_PROFILE (
  echo 错误: _backend-common.cmd 需要 profile 参数 >&2
  exit /b 1
)

set "MINERVA_BACKEND_DIR=%~dp0..\backend"
set "APP_ENV=%MINERVA_PROFILE%"
set "MINERVA_ENV_FILE=%MINERVA_BACKEND_DIR%\.env.%MINERVA_PROFILE%"

if not exist "%MINERVA_ENV_FILE%" (
  echo 错误: 未找到环境文件 %MINERVA_ENV_FILE% >&2
  echo 提示: copy backend\.env.example backend\.env.%MINERVA_PROFILE% >&2
  exit /b 1
)

set "MINERVA_PYTHON="
if exist "%MINERVA_BACKEND_DIR%\minerva\Scripts\python.exe" (
  set "MINERVA_PYTHON=%MINERVA_BACKEND_DIR%\minerva\Scripts\python.exe"
  goto :python_done
)
where py >nul 2>&1 && (
  py -3.13 -c "import sys" 2>nul && if not errorlevel 1 set "MINERVA_PYTHON=py -3.13" && goto :python_done
  py -3.12 -c "import sys" 2>nul && if not errorlevel 1 set "MINERVA_PYTHON=py -3.12" && goto :python_done
  py -3.11 -c "import sys" 2>nul && if not errorlevel 1 set "MINERVA_PYTHON=py -3.11" && goto :python_done
)
set "MINERVA_PYTHON=python"

:python_done
if not defined MINERVA_PYTHON (
  echo 错误: 未找到 Python 解释器 >&2
  exit /b 1
)

cd /d "%MINERVA_BACKEND_DIR%" || exit /b 1
echo 环境: APP_ENV=%APP_ENV%  文件: %MINERVA_ENV_FILE%
echo Python: %MINERVA_PYTHON%
endlocal & (
  set "APP_ENV=%MINERVA_PROFILE%"
  set "MINERVA_BACKEND_DIR=%MINERVA_BACKEND_DIR%"
  set "MINERVA_PYTHON=%MINERVA_PYTHON%"
  set "MINERVA_ENV_FILE=%MINERVA_ENV_FILE%"
)
exit /b 0
```

> **注意：** `endlocal & (...)` 将变量传回父脚本；`run-backend.cmd` / `run-celery.cmd` 须在 `setlocal` 之后 `call` 本文件。

- [ ] **Step 2: 重写 `scripts/run-backend.cmd`**

```bat
@echo off
setlocal EnableExtensions
chcp 65001 >nul
REM 启动 FastAPI（仅 uvicorn）。用法: run-backend.cmd [profile]  默认 local
REM 环境变量: MINERVA_BACKEND_PORT（默认 8000）

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=local"
if not defined MINERVA_BACKEND_PORT set "MINERVA_BACKEND_PORT=8000"

call "%~dp0_backend-common.cmd" "%PROFILE%"
if errorlevel 1 exit /b 1

echo 目录: %MINERVA_BACKEND_DIR%  端口: %MINERVA_BACKEND_PORT%
"%MINERVA_PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
exit /b %ERRORLEVEL%
```

- [ ] **Step 3: 创建 `scripts/run-celery.cmd`**

```bat
@echo off
setlocal EnableExtensions
chcp 65001 >nul
REM 用法: run-celery.cmd <profile> <worker|beat>
REM Windows: 每次调用打开独立 cmd 窗口；MINERVA_CELERY_USE_PREFORK=1 可启用 prefork

if "%~2"=="" goto :usage
if not "%~3"=="" goto :usage

set "PROFILE=%~1"
set "SUBCMD=%~2"

if /i not "%SUBCMD%"=="worker" if /i not "%SUBCMD%"=="beat" (
  echo 错误: 子命令必须是 worker 或 beat，收到: %SUBCMD% >&2
  goto :usage
)

call "%~dp0_backend-common.cmd" "%PROFILE%"
if errorlevel 1 exit /b 1

set "CELERY_APP=app.celery_app:celery_app"
if /i "%SUBCMD%"=="worker" (
  set "WIN_TITLE=Minerva Celery Worker"
) else (
  set "WIN_TITLE=Minerva Celery Beat"
)

start "%WIN_TITLE%" cmd /k "cd /d ""%MINERVA_BACKEND_DIR%"" && set APP_ENV=%APP_ENV% && ""%MINERVA_PYTHON%"" -m celery -A %CELERY_APP% %SUBCMD% --loglevel=INFO"
exit /b 0

:usage
echo 用法: run-celery.cmd ^<profile^> ^<worker^|beat^> >&2
echo   profile  环境名，对应 backend\.env.^<profile^> >&2
echo   子命令   worker 或 beat（须同时跑两者时请各执行一次） >&2
echo. >&2
echo 示例: >&2
echo   run-celery.cmd local worker >&2
echo   run-celery.cmd local beat >&2
exit /b 1
```

- [ ] **Step 4: 手动冒烟**

Run: `scripts\run-celery.cmd`  
Expected: 用法 + exit 1

Run: `scripts\run-celery.cmd local worker`（有 `.env.local` 时）  
Expected: 弹出标题为 `Minerva Celery Worker` 的新窗口

- [ ] **Step 5: Commit**

```bash
git add scripts/_backend-common.cmd scripts/run-backend.cmd scripts/run-celery.cmd
git commit -m "feat(scripts): split celery to run-celery.cmd, shared windows common"
```

---

### Task 4: 文档与约定同步

**Files:**
- Modify: `backend/.env.example`（头部约 12 行）
- Modify: `README.md`、`README.en.md`
- Modify: `.cursor/skills/minerva-conventions/SKILL.md`
- Modify: `scripts/run-frontend.sh`、`scripts/run-frontend.cmd`（各 1 行注释）

- [ ] **Step 1: 更新 `backend/.env.example` 头注释**

替换加载说明为：

```ini
# 应用通过 app/config.py（Pydantic Settings）加载配置，优先级：
#   1. 进程环境变量（shell / 启动脚本 / IDE / CI）
#   2. backend/.env.<APP_ENV>  单个文件（无叠加）
#
# 本地默认：复制为 .env.local 后修改（run-backend 无参即加载）
# 团队 dev：复制为 .env.dev，使用 run-backend dev / run-celery dev worker
```

- [ ] **Step 2: 更新 `README.md` 启动章节（中文）**

在「启动后端」处改为类似：

```markdown
### 后端

1. 复制环境配置：`cp backend/.env.example backend/.env.local`
2. 启动 API：`scripts/run-backend.cmd`（Windows）或 `bash scripts/run-backend.sh`（Linux/macOS）
3. 启动 Celery（需 Redis；定时任务另需 Beat）：
   - `scripts/run-celery.cmd local worker` 与 `scripts/run-celery.cmd local beat`
   - 或 `bash scripts/run-celery.sh local worker` / `local beat`
4. 使用远程 dev 库：`run-backend dev`、`run-celery dev worker` 等（对应 `backend/.env.dev`）

可选：`MINERVA_BACKEND_PORT` 覆盖 API 端口（默认 8000）。
```

同步更新 `README.en.md` 英文对应段落。

删除或替换文中 `MINERVA_SKIP_CELERY_*`、仅 `run-backend` 即含 Celery 的描述。

- [ ] **Step 3: 更新 `minerva-conventions` §3**

- 加载顺序改为：进程环境变量 → `.env.<APP_ENV>`（单文件）
- 默认 profile：`local` → `.env.local`
- 启动脚本列表：`run-backend`、`run-celery`；删除 `MINERVA_SKIP_CELERY_*`
- 验证命令示例：`APP_ENV=dev python -c "from app.config import settings; print(settings.app_env, settings.database_url[:40])"`

- [ ] **Step 4: 更新 `run-frontend` 注释**

`run-frontend.sh` 第 3 行、`run-frontend.cmd` 第 4 行：注明需先启动 `run-backend`（API）及按需 `run-celery`。

- [ ] **Step 5: 全库 grep 确认无遗留**

Run: `rg "MINERVA_SKIP_CELERY|\.env\.dev\." --glob "!docs/superpowers/specs/*" .`

Expected: 无匹配（spec 历史描述可保留在 design 文档的「废弃」小节）

- [ ] **Step 6: Commit**

```bash
git add backend/.env.example README.md README.en.md .cursor/skills/minerva-conventions/SKILL.md scripts/run-frontend.sh scripts/run-frontend.cmd
git commit -m "docs: document split startup scripts and single-profile env files"
```

---

### Task 5: Spec 回填与验收

**Files:**
- Modify: `docs/superpowers/specs/2026-05-19-startup-scripts-design.md`

- [ ] **Step 1: 运行 config 单元测试**

Run: `cd backend && pytest tests/test_config_env_loading.py -v`

Expected: 全部 PASS

- [ ] **Step 2: 验证 config 加载（本机有 `.env.dev` / `.env.local` 时）**

Run:

```bash
cd backend
set APP_ENV=dev
python -c "from importlib import reload; import app.config as c; reload(c); from app.config import settings; print(settings.app_env)"
```

Expected: `dev`（且 `database_url` 来自 `.env.dev`，非 local）

- [ ] **Step 3: 更新 spec §7 清单为 `[x]`，§9 实现对照填路径与「已实现」**

- [ ] **Step 4: 将 spec 文首状态改为「已实现（2026-05-19）」**

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-05-19-startup-scripts-design.md
git commit -m "docs: mark startup scripts spec implemented"
```

---

## Plan self-review（已完成）

| 检查项 | 结果 |
|--------|------|
| Spec §3 CLI（无 both、严格两参数 celery） | Task 2/3 `run-celery` |
| 默认 local / 单文件加载 | Task 1 + common |
| 删除 MINERVA_SKIP_CELERY | Task 2–4 grep |
| Win 独立窗口 | Task 3 `start cmd /k` |
| 文档同步 | Task 4 |
| 无 TBD 步骤 | 通过 |
