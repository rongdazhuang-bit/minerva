@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Install GraphKB LightRAG + GraphRAG workers into workers\graph-kb-*\.venv
REM Usage: install-graph-kb-workers.cmd
REM Env: MINERVA_GRAPH_KB_WORKERS=lightrag,graphrag  (default both)
REM      MINERVA_SKIP_VENV_BOOTSTRAP=1  fail if .venv missing

set "REPO_ROOT=%~dp0.."
if not defined MINERVA_GRAPH_KB_WORKERS set "MINERVA_GRAPH_KB_WORKERS=lightrag,graphrag"

for %%T in (%MINERVA_GRAPH_KB_WORKERS:,= %) do (
  call :install_one %%T
  if errorlevel 1 exit /b 1
)
echo [install-graph-kb-workers] done
exit /b 0

:install_one
set "WORKER_NAME=%~1"
set "WORKER_DIR=%REPO_ROOT%\backend\workers\graph-kb-%WORKER_NAME%"
if not exist "%WORKER_DIR%\pyproject.toml" (
  echo [error] missing %WORKER_DIR%\pyproject.toml
  exit /b 1
)

set "PIP_PY=%WORKER_DIR%\.venv\Scripts\python.exe"
if not exist "%PIP_PY%" (
  if "%MINERVA_SKIP_VENV_BOOTSTRAP%"=="1" (
    echo [error] %WORKER_DIR%\.venv not found
    exit /b 1
  )
  echo [venv] creating %WORKER_DIR%\.venv ...
  py -3.13 -m venv "%WORKER_DIR%\.venv" 2>nul || py -3 -m venv "%WORKER_DIR%\.venv" || python -m venv "%WORKER_DIR%\.venv"
  if not exist "%PIP_PY%" (
    echo [error] failed to create venv under %WORKER_DIR%
    exit /b 1
  )
)

echo [install-graph-kb-workers] %WORKER_NAME%: %PIP_PY%
"%PIP_PY%" -m pip install -U pip wheel
pushd "%WORKER_DIR%"
"%PIP_PY%" -m pip install -e ".[dev,engine]"
set "INSTALL_ERR=%ERRORLEVEL%"
popd
if not "%INSTALL_ERR%"=="0" exit /b %INSTALL_ERR%

if /I "%WORKER_NAME%"=="lightrag" (
  "%PIP_PY%" -c "import lightrag; import asyncpg; import pgvector" 2>nul || (
    echo [error] lightrag engine import check failed
    exit /b 1
  )
) else if /I "%WORKER_NAME%"=="graphrag" (
  "%PIP_PY%" -c "import graphrag; import pandas; import pyarrow" 2>nul || (
    echo [error] graphrag engine import check failed
    exit /b 1
  )
) else (
  echo [error] unknown worker %WORKER_NAME%
  exit /b 1
)
echo [install-graph-kb-workers] %WORKER_NAME%: engine import OK
exit /b 0
