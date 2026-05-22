@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Start FastAPI (uvicorn). Usage: run-backend.cmd [profile]  default local
REM Default Python: backend\.venv\Scripts\python.exe
REM Env: MINERVA_BACKEND_PORT (default 8000), MINERVA_PYTHON, MINERVA_ALLOW_SYSTEM_PYTHON

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=local"
if not defined MINERVA_BACKEND_PORT set "MINERVA_BACKEND_PORT=8000"

set "MINERVA_BACKEND_DIR=%~dp0..\backend"
if not defined MINERVA_PYTHON (
  set "MINERVA_PYTHON=%MINERVA_BACKEND_DIR%\.venv\Scripts\python.exe"
)

call "%~dp0_backend-common.cmd" "%PROFILE%"
if errorlevel 1 exit /b 1

echo [run-backend] dir: %MINERVA_BACKEND_DIR%  port: %MINERVA_BACKEND_PORT%
"%MINERVA_PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
exit /b %ERRORLEVEL%
