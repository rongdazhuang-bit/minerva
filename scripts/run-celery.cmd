@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM 用法: run-celery.cmd <profile> <worker|beat>
REM Windows: 每次调用打开独立 cmd 窗口；MINERVA_CELERY_USE_PREFORK=1 可启用 prefork（见 app.celery_app）

if "%~2"=="" goto :usage
if not "%~3"=="" goto :usage

set "PROFILE=%~1"
set "SUBCMD=%~2"

if /i not "%SUBCMD%"=="worker" if /i not "%SUBCMD%"=="beat" (
  echo 错误: 子命令必须是 worker 或 beat，收到: %SUBCMD% >&2
  goto :usage
)

call "%~dp0_backend-common.cmd" "%PROFILE%"
if errorlevel 1 exit /b 1

set "CELERY_APP=app.celery_app:celery_app"
if /i "%SUBCMD%"=="worker" (
  set "WIN_TITLE=Minerva Celery Worker"
) else (
  set "WIN_TITLE=Minerva Celery Beat"
)

start "%WIN_TITLE%" cmd /k "cd /d ""%MINERVA_BACKEND_DIR%"" && set APP_ENV=%APP_ENV% && ""%MINERVA_PYTHON%"" -m celery -A %CELERY_APP% %SUBCMD% --loglevel=INFO"
exit /b 0

:usage
echo 用法: run-celery.cmd ^<profile^> ^<worker^|beat^> >&2
echo   profile  环境名，对应 backend\.env.^<profile^> >&2
echo   子命令   worker 或 beat（须同时跑两者时请各执行一次） >&2
echo. >&2
echo 示例: >&2
echo   run-celery.cmd local worker >&2
echo   run-celery.cmd local beat >&2
exit /b 1
