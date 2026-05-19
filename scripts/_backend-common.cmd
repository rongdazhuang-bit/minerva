@echo off
REM 由 run-backend.cmd / run-celery.cmd 调用: call _backend-common.cmd <profile>
REM 设置 APP_ENV、MINERVA_BACKEND_DIR、MINERVA_PYTHON、MINERVA_ENV_FILE
setlocal EnableExtensions

set "MINERVA_PROFILE=%~1"
if not defined MINERVA_PROFILE (
  echo 错误: _backend-common.cmd 需要 profile 参数 >&2
  exit /b 1
)

set "MINERVA_BACKEND_DIR=%~dp0..\backend"
set "APP_ENV=%MINERVA_PROFILE%"
set "MINERVA_ENV_FILE=%MINERVA_BACKEND_DIR%\.env.%MINERVA_PROFILE%"

if not exist "%MINERVA_ENV_FILE%" (
  echo 错误: 未找到环境文件 %MINERVA_ENV_FILE% >&2
  echo 提示: copy backend\.env.example backend\.env.%MINERVA_PROFILE% >&2
  exit /b 1
)

set "MINERVA_PYTHON="
if exist "%MINERVA_BACKEND_DIR%\minerva\Scripts\python.exe" (
  set "MINERVA_PYTHON=%MINERVA_BACKEND_DIR%\minerva\Scripts\python.exe"
  goto :python_done
)
where py >nul 2>&1 && (
  py -3.13 -c "import sys" 2>nul && if not errorlevel 1 set "MINERVA_PYTHON=py -3.13" && goto :python_done
  py -3.12 -c "import sys" 2>nul && if not errorlevel 1 set "MINERVA_PYTHON=py -3.12" && goto :python_done
  py -3.11 -c "import sys" 2>nul && if not errorlevel 1 set "MINERVA_PYTHON=py -3.11" && goto :python_done
)
set "MINERVA_PYTHON=python"

:python_done
if not defined MINERVA_PYTHON (
  echo 错误: 未找到 Python 解释器 >&2
  exit /b 1
)

cd /d "%MINERVA_BACKEND_DIR%" || exit /b 1
echo 环境: APP_ENV=%APP_ENV%  文件: %MINERVA_ENV_FILE%
echo Python: %MINERVA_PYTHON%

endlocal & set "APP_ENV=%MINERVA_PROFILE%" & set "MINERVA_BACKEND_DIR=%MINERVA_BACKEND_DIR%" & set "MINERVA_PYTHON=%MINERVA_PYTHON%" & set "MINERVA_ENV_FILE=%MINERVA_ENV_FILE%"
exit /b 0
