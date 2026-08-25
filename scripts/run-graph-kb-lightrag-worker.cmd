@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Start GraphKB LightRAG worker on 127.0.0.1:8101
REM Usage: run-graph-kb-lightrag-worker.cmd
REM Prereq (real engine): scripts\install-graph-kb-workers.cmd  (or only lightrag via MINERVA_GRAPH_KB_WORKERS=lightrag)
REM Env: GRAPH_KB_LIGHTRAG_WORKER_API_KEY (required) must match backend/.env.dev
REM      GRAPH_KB_WORKER_FAKE=1 skips LightRAG SDK (in-memory fake)
REM      GRAPH_KB_LIGHTRAG_DATABASE_URL for real PG-backed mode
REM      GRAPH_KB_DATA (optional) silo parent; default backend\data\graph_kb

if not defined GRAPH_KB_DATA (
  set "GRAPH_KB_DATA=%~dp0..\backend\data\graph_kb"
)

set "WORKER_DIR=%~dp0..\workers\graph-kb-lightrag"
set "WORKER_VENV=%WORKER_DIR%\.venv\Scripts\python.exe"

if exist "%WORKER_VENV%" (
  set "MINERVA_PYTHON=%WORKER_VENV%"
) else if "%GRAPH_KB_WORKER_FAKE%"=="1" (
  if exist "%~dp0..\backend\.venv\Scripts\python.exe" (
    set "MINERVA_PYTHON=%~dp0..\backend\.venv\Scripts\python.exe"
  ) else (
    set "MINERVA_PYTHON=python"
  )
) else (
  echo [error] LightRAG worker venv not found: %WORKER_VENV%
  echo [hint] run scripts\install-graph-kb-workers.cmd
  echo [hint] or set GRAPH_KB_WORKER_FAKE=1 for fake mode without lightrag-hku
  exit /b 1
)

cd /d "%WORKER_DIR%"
echo [run-graph-kb-lightrag-worker] dir: %CD%  port: 8101  python: %MINERVA_PYTHON%
"%MINERVA_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8101
exit /b %ERRORLEVEL%
