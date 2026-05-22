@echo off
REM 由 run-backend.cmd / run-celery.cmd 调用: call _backend-common.cmd <profile>
REM 设置 APP_ENV、MINERVA_BACKEND_DIR、MINERVA_PYTHON（始终为 .exe 路径）、MINERVA_ENV_FILE
REM 勿在本文件使用 setlocal，以便变量回传到调用方。

set "MINERVA_PROFILE=%~1"
if not defined MINERVA_PROFILE (
  echo 错误: _backend-common.cmd 需要 profile 参数 >&2
  exit /b 1
)

set "MINERVA_BACKEND_DIR=%~dp0..\backend"
call :resolve_backend_dir "%MINERVA_BACKEND_DIR%"
set "APP_ENV=%MINERVA_PROFILE%"
set "MINERVA_ENV_FILE=%MINERVA_BACKEND_DIR%\.env.%MINERVA_PROFILE%"

if not exist "%MINERVA_ENV_FILE%" (
  echo 错误: 未找到环境文件 %MINERVA_ENV_FILE% >&2
  echo 提示: copy backend\.env.example backend\.env.%MINERVA_PROFILE% >&2
  exit /b 1
)

set "MINERVA_PYTHON="
if exist "%MINERVA_BACKEND_DIR%\.venv\Scripts\python.exe" (
  set "MINERVA_PYTHON=%MINERVA_BACKEND_DIR%\.venv\Scripts\python.exe"
  goto :python_done
)

where py >nul 2>&1 && call :try_py_launcher 3.13
if not defined MINERVA_PYTHON where py >nul 2>&1 && call :try_py_launcher 3.12
if not defined MINERVA_PYTHON where py >nul 2>&1 && call :try_py_launcher 3.11

if not defined MINERVA_PYTHON (
  where python >nul 2>&1 && for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined MINERVA_PYTHON set "MINERVA_PYTHON=%%i"
  )
)

:python_done
if not defined MINERVA_PYTHON (
  echo 错误: 未找到 Python 解释器 >&2
  exit /b 1
)

cd /d "%MINERVA_BACKEND_DIR%" || exit /b 1
echo 环境: APP_ENV=%APP_ENV%  文件: %MINERVA_ENV_FILE%
echo Python: %MINERVA_PYTHON%
exit /b 0

:try_py_launcher
py -%1 -c "import sys" 2>nul || exit /b 0
set "_PY_EXE="
for /f "usebackq tokens=* delims=" %%i in (`py -%1 -c "import sys; print(sys.executable)" 2^>nul`) do set "_PY_EXE=%%i"
if defined _PY_EXE set "MINERVA_PYTHON=%_PY_EXE%"
set "_PY_EXE="
exit /b 0

:resolve_backend_dir
set "MINERVA_BACKEND_DIR=%~f1"
exit /b 0
