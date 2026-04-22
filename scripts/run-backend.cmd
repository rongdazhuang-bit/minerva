@echo off
setlocal EnableExtensions
chcp 65001 >nul
REM 在仓库根目录从「资源管理器」或 cmd 运行本脚本：启动 FastAPI 后端
REM 环境变量：APP_ENV、MINERVA_BACKEND_PORT（覆盖端口，默认 8000）

set "BACKEND=%~dp0..\backend"
if not defined MINERVA_BACKEND_PORT set "MINERVA_BACKEND_PORT=8000"

cd /d "%BACKEND%" || exit /b 1

echo 目录: %BACKEND%  端口: %MINERVA_BACKEND_PORT%

if exist "%BACKEND%\.venv\Scripts\python.exe" (
  "%BACKEND%\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1 && (
  py -3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
  exit /b %ERRORLEVEL%
)

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
exit /b %ERRORLEVEL%
