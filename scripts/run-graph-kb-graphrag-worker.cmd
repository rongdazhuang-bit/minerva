@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Start GraphKB GraphRAG worker on 127.0.0.1:8102
REM Usage: run-graph-kb-graphrag-worker.cmd
REM Env: GRAPH_KB_WORKER_FAKE=1 skips GraphRAG SDK (writes {root}/fake.json)
REM      GRAPH_KB_DATA (optional) GraphRAG silo parent; default backend\data\graph_kb

if not defined GRAPH_KB_DATA (
  set "GRAPH_KB_DATA=%~dp0..\backend\data\graph_kb"
)

set "WORKER_DIR=%~dp0..\workers\graph-kb-graphrag"
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
echo [run-graph-kb-graphrag-worker] dir: %CD%  port: 8102
"%MINERVA_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8102
exit /b %ERRORLEVEL%
