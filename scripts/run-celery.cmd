@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Usage: run-celery.cmd <profile> <worker|beat>
REM Default Python: backend\.venv\Scripts\python.exe
REM Windows worker pool default: threads (MINERVA_CELERY_POOL / MINERVA_CELERY_CONCURRENCY)

if "%~2"=="" goto :usage
if not "%~3"=="" goto :usage

set "PROFILE=%~1"
set "SUBCMD=%~2"

if /i not "%SUBCMD%"=="worker" if /i not "%SUBCMD%"=="beat" (
  echo [error] subcommand must be worker or beat, got: %SUBCMD% >&2
  goto :usage
)

set "MINERVA_BACKEND_DIR=%~dp0..\backend"
if not defined MINERVA_PYTHON (
  set "MINERVA_PYTHON=%MINERVA_BACKEND_DIR%\.venv\Scripts\python.exe"
)

call "%~dp0_backend-common.cmd" "%PROFILE%"
if errorlevel 1 exit /b 1

set "CELERY_APP=app.celery_app:celery_app"
if not defined MINERVA_CELERY_POOL set "MINERVA_CELERY_POOL=threads"
if not defined MINERVA_CELERY_CONCURRENCY set "MINERVA_CELERY_CONCURRENCY=4"
if not defined MINERVA_CELERY_QUEUES set "MINERVA_CELERY_QUEUES=default,dataset,graph_kb"
echo [run-celery] dir: %MINERVA_BACKEND_DIR%  subcmd: %SUBCMD%
"%MINERVA_PYTHON%" -m app.sys.celery.service.broker_preflight
if errorlevel 1 exit /b 1
if /i "%SUBCMD%"=="worker" (
  "%MINERVA_PYTHON%" -m celery -A %CELERY_APP% worker --loglevel=INFO --pool=%MINERVA_CELERY_POOL% --concurrency=%MINERVA_CELERY_CONCURRENCY% -Q %MINERVA_CELERY_QUEUES%
) else (
  "%MINERVA_PYTHON%" -m celery -A %CELERY_APP% beat --loglevel=INFO
)
exit /b %ERRORLEVEL%

:usage
echo Usage: run-celery.cmd ^<profile^> ^<worker^|beat^> >&2
echo   profile   env name, maps to backend\.env.^<profile^> >&2
echo   subcmd    worker or beat (run twice for both) >&2
echo. >&2
echo Examples: >&2
echo   run-celery.cmd local worker >&2
echo   run-celery.cmd local beat >&2
exit /b 1
