@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Start GraphKB LightRAG worker on 127.0.0.1:8101
REM Usage: run-graph-kb-lightrag-worker.cmd
REM Prereq (real engine): scripts\install-graph-kb-workers.cmd
REM Config: backend\workers\graph-kb-lightrag\.env.<WORKER_ENV> (default WORKER_ENV=dev)

if not defined WORKER_ENV (
  set "WORKER_ENV=dev"
)

set "WORKER_DIR=%~dp0..\backend\workers\graph-kb-lightrag"
set "WORKER_VENV=%WORKER_DIR%\.venv\Scripts\python.exe"

if exist "%WORKER_VENV%" (
  set "MINERVA_PYTHON=%WORKER_VENV%"
) else if exist "%WORKER_DIR%\.env.dev" (
  findstr /B /C:"GRAPH_KB_WORKER_FAKE=1" "%WORKER_DIR%\.env.dev" >nul 2>&1
  if not errorlevel 1 (
    if exist "%~dp0..\backend\.venv\Scripts\python.exe" (
      set "MINERVA_PYTHON=%~dp0..\backend\.venv\Scripts\python.exe"
    ) else (
      set "MINERVA_PYTHON=python"
    )
  ) else (
    echo [error] LightRAG worker venv not found: %WORKER_VENV%
    echo [hint] run scripts\install-graph-kb-workers.cmd
    exit /b 1
  )
) else (
  echo [error] LightRAG worker venv not found: %WORKER_VENV%
  echo [hint] run scripts\install-graph-kb-workers.cmd
  exit /b 1
)

cd /d "%WORKER_DIR%"
echo [run-graph-kb-lightrag-worker] dir: %CD%  WORKER_ENV: %WORKER_ENV%  port: 8101  python: %MINERVA_PYTHON%
"%MINERVA_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8101
exit /b %ERRORLEVEL%
