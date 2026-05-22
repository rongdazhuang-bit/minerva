@echo off
chcp 65001 >nul 2>&1
REM Called by run-backend.cmd / run-celery.cmd: call _backend-common.cmd <profile>
REM Sets APP_ENV, MINERVA_BACKEND_DIR, MINERVA_PYTHON (backend\.venv by default), MINERVA_ENV_FILE
REM Do not use setlocal here so variables return to the caller.

set "MINERVA_PROFILE=%~1"
if not defined MINERVA_PROFILE (
  echo [error] _backend-common.cmd requires profile argument >&2
  exit /b 1
)

if not defined MINERVA_BACKEND_DIR (
  set "MINERVA_BACKEND_DIR=%~dp0..\backend"
)
call :resolve_backend_dir "%MINERVA_BACKEND_DIR%"
set "APP_ENV=%MINERVA_PROFILE%"
set "MINERVA_ENV_FILE=%MINERVA_BACKEND_DIR%\.env.%MINERVA_PROFILE%"

if not exist "%MINERVA_ENV_FILE%" (
  echo [error] env file not found: %MINERVA_ENV_FILE% >&2
  echo [hint] copy backend\.env.example backend\.env.%MINERVA_PROFILE% >&2
  exit /b 1
)

set "MINERVA_VENV_PYTHON=%MINERVA_BACKEND_DIR%\.venv\Scripts\python.exe"

if defined MINERVA_PYTHON (
  if not exist "%MINERVA_PYTHON%" (
    echo [error] MINERVA_PYTHON not found: %MINERVA_PYTHON% >&2
    exit /b 1
  )
  goto :python_done
)

if exist "%MINERVA_VENV_PYTHON%" (
  set "MINERVA_PYTHON=%MINERVA_VENV_PYTHON%"
  goto :python_done
)

if "%MINERVA_ALLOW_SYSTEM_PYTHON%"=="1" (
  where py >nul 2>&1 && call :try_py_launcher 3.13
  if not defined MINERVA_PYTHON where py >nul 2>&1 && call :try_py_launcher 3.12
  if not defined MINERVA_PYTHON where py >nul 2>&1 && call :try_py_launcher 3.11
  if not defined MINERVA_PYTHON (
    where python >nul 2>&1 && for /f "delims=" %%i in ('where python 2^>nul') do (
      if not defined MINERVA_PYTHON set "MINERVA_PYTHON=%%i"
    )
  )
  if defined MINERVA_PYTHON goto :python_done
)

echo [error] backend\.venv not found: %MINERVA_VENV_PYTHON% >&2
echo [hint] cd backend ^& py -3.13 -m venv .venv ^& .venv\Scripts\pip install -e ".[dev]" >&2
echo [hint] or set MINERVA_ALLOW_SYSTEM_PYTHON=1 to use system Python >&2
exit /b 1

:python_done
cd /d "%MINERVA_BACKEND_DIR%" || exit /b 1
echo [env] APP_ENV=%APP_ENV%  file=%MINERVA_ENV_FILE%
echo [python] %MINERVA_PYTHON%
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
