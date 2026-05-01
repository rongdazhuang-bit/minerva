@echo off
setlocal EnableExtensions
chcp 65001 >nul
REM 在仓库根目录从「资源管理器」或 cmd 运行本脚本：启动 FastAPI 后端；可选同时拉起 Celery Worker（独立窗口）
REM 环境变量：APP_ENV、MINERVA_BACKEND_PORT（覆盖端口，默认 8000）
REM 可选：MINERVA_SKIP_CELERY_WORKER=1 不拉起 Worker；MINERVA_SKIP_CELERY_BEAT=1 不拉起 Beat（定时任务依赖 Beat）。
REM Windows 下 Worker 默认 ``solo`` 进程池（见 ``app.celery_app``）；若要 prefork：MINERVA_CELERY_USE_PREFORK=1。
REM Beat 定时从 Postgres 加载 ``enabled`` + ``cron`` 的 ``sys_celery``，通过 broker 派发任务。
REM
REM 勿用「py -3」作无 venv 时的唯一回退：若本机将 Python 3.13 自由线程版 (python3.13t.exe) 设为主版本，
REM 「py -3」会选到 3.13t；pydantic-core 等常无 3.13t 的预编译 wheel，会报
REM   ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
REM 故依次尝试「py -3.13 / -3.12 / -3.11」（标准解释器）后再用「python -m」。

set "BACKEND=%~dp0..\backend"
if not defined MINERVA_BACKEND_PORT set "MINERVA_BACKEND_PORT=8000"

cd /d "%BACKEND%" || exit /b 1

echo 目录: %BACKEND%  端口: %MINERVA_BACKEND_PORT%

if exist "%BACKEND%\.venv\Scripts\python.exe" (
  if /i not "%MINERVA_SKIP_CELERY_WORKER%"=="1" (
    start "Minerva Celery Worker" cmd /k "cd /d ""%BACKEND%"" && ""%BACKEND%\.venv\Scripts\python.exe"" -m celery -A app.celery_app:celery_app worker --loglevel=INFO"
  )
  if /i not "%MINERVA_SKIP_CELERY_BEAT%"=="1" (
    start "Minerva Celery Beat" cmd /k "cd /d ""%BACKEND%"" && ""%BACKEND%\.venv\Scripts\python.exe"" -m celery -A app.celery_app:celery_app beat --loglevel=INFO"
  )
  "%BACKEND%\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1 && (
  py -3.13 -c "import sys" 2>nul
  if not errorlevel 1 (
    if /i not "%MINERVA_SKIP_CELERY_WORKER%"=="1" (
      start "Minerva Celery Worker" cmd /k "cd /d ""%BACKEND%"" && py -3.13 -m celery -A app.celery_app:celery_app worker --loglevel=INFO"
    )
    if /i not "%MINERVA_SKIP_CELERY_BEAT%"=="1" (
      start "Minerva Celery Beat" cmd /k "cd /d ""%BACKEND%"" && py -3.13 -m celery -A app.celery_app:celery_app beat --loglevel=INFO"
    )
    py -3.13 -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
    exit /b %ERRORLEVEL%
  )
  py -3.12 -c "import sys" 2>nul
  if not errorlevel 1 (
    if /i not "%MINERVA_SKIP_CELERY_WORKER%"=="1" (
      start "Minerva Celery Worker" cmd /k "cd /d ""%BACKEND%"" && py -3.12 -m celery -A app.celery_app:celery_app worker --loglevel=INFO"
    )
    if /i not "%MINERVA_SKIP_CELERY_BEAT%"=="1" (
      start "Minerva Celery Beat" cmd /k "cd /d ""%BACKEND%"" && py -3.12 -m celery -A app.celery_app:celery_app beat --loglevel=INFO"
    )
    py -3.12 -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
    exit /b %ERRORLEVEL%
  )
  py -3.11 -c "import sys" 2>nul
  if not errorlevel 1 (
    if /i not "%MINERVA_SKIP_CELERY_WORKER%"=="1" (
      start "Minerva Celery Worker" cmd /k "cd /d ""%BACKEND%"" && py -3.11 -m celery -A app.celery_app:celery_app worker --loglevel=INFO"
    )
    if /i not "%MINERVA_SKIP_CELERY_BEAT%"=="1" (
      start "Minerva Celery Beat" cmd /k "cd /d ""%BACKEND%"" && py -3.11 -m celery -A app.celery_app:celery_app beat --loglevel=INFO"
    )
    py -3.11 -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
    exit /b %ERRORLEVEL%
  )
)

if /i not "%MINERVA_SKIP_CELERY_WORKER%"=="1" (
  start "Minerva Celery Worker" cmd /k "cd /d ""%BACKEND%"" && python -m celery -A app.celery_app:celery_app worker --loglevel=INFO"
)
if /i not "%MINERVA_SKIP_CELERY_BEAT%"=="1" (
  start "Minerva Celery Beat" cmd /k "cd /d ""%BACKEND%"" && python -m celery -A app.celery_app:celery_app beat --loglevel=INFO"
)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
exit /b %ERRORLEVEL%
