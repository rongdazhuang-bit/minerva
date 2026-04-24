@echo off
setlocal EnableExtensions
chcp 65001 >nul
REM 在仓库根目录从「资源管理器」或 cmd 运行本脚本：启动 FastAPI 后端
REM 环境变量：APP_ENV、MINERVA_BACKEND_PORT（覆盖端口，默认 8000）
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
  "%BACKEND%\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1 && (
  py -3.13 -c "import sys" 2>nul
  if not errorlevel 1 (
    py -3.13 -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
    exit /b %ERRORLEVEL%
  )
  py -3.12 -c "import sys" 2>nul
  if not errorlevel 1 (
    py -3.12 -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
    exit /b %ERRORLEVEL%
  )
  py -3.11 -c "import sys" 2>nul
  if not errorlevel 1 (
    py -3.11 -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
    exit /b %ERRORLEVEL%
  )
)

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port %MINERVA_BACKEND_PORT%
exit /b %ERRORLEVEL%
