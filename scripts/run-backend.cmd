@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM 启动 FastAPI（仅 uvicorn）。用法: run-backend.cmd [profile]  默认 local
REM 环境变量: MINERVA_BACKEND_PORT（默认 8000）
REM 局域网：--host 0.0.0.0，其它设备可访问 http://<本机IP>:端口（开发环境 CORS 含私网段）。

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=local"
if not defined MINERVA_BACKEND_PORT set "MINERVA_BACKEND_PORT=8000"

call "%~dp0_backend-common.cmd" "%PROFILE%"
if errorlevel 1 exit /b 1

echo 目录: %MINERVA_BACKEND_DIR%  端口: %MINERVA_BACKEND_PORT%
"%MINERVA_PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
exit /b %ERRORLEVEL%
