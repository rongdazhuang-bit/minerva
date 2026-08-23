@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Start GraphKB LightRAG worker on 127.0.0.1:8101
REM Usage: run-graph-kb-lightrag-worker.cmd
REM Env: GRAPH_KB_WORKER_FAKE=1 skips LightRAG SDK (in-memory fake)
REM      GRAPH_KB_LIGHTRAG_DATABASE_URL for real PG-backed mode

set "WORKER_DIR=%~dp0..\workers\graph-kb-lightrag"
if not defined MINERVA_PYTHON (
  if exist "%WORKER_DIR%\.venv\Scripts\python.exe" (
    set "MINERVA_PYTHON=%WORKER_DIR%\.venv\Scripts\python.exe"
  ) else if exist "%~dp0..\backend\.venv\Scripts\python.exe" (
    set "MINERVA_PYTHON=%~dp0..\backend\.venv\Scripts\python.exe"
  ) else (
    set "MINERVA_PYTHON=python"
  )
)

cd /d "%WORKER_DIR%"
echo [run-graph-kb-lightrag-worker] dir: %CD%  port: 8101
"%MINERVA_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8101
exit /b %ERRORLEVEL%
