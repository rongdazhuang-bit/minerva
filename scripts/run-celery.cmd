@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM 用法: run-celery.cmd <profile> <worker|beat>
REM 在当前 cmd 窗口前台运行；Windows 推荐 threads 池（MINERVA_CELERY_POOL / MINERVA_CELERY_CONCURRENCY）。
REM MINERVA_CELERY_USE_PREFORK=1 等价于 MINERVA_CELERY_POOL=prefork（见 app.celery_app）。

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
if not defined MINERVA_CELERY_POOL set "MINERVA_CELERY_POOL=threads"
if not defined MINERVA_CELERY_CONCURRENCY set "MINERVA_CELERY_CONCURRENCY=4"
echo 目录: %MINERVA_BACKEND_DIR%  子命令: %SUBCMD%
"%MINERVA_PYTHON%" -m app.sys.celery.service.broker_preflight
if errorlevel 1 exit /b 1
if /i "%SUBCMD%"=="worker" (
  "%MINERVA_PYTHON%" -m celery -A %CELERY_APP% worker --loglevel=INFO --pool=%MINERVA_CELERY_POOL% --concurrency=%MINERVA_CELERY_CONCURRENCY%
) else (
  "%MINERVA_PYTHON%" -m celery -A %CELERY_APP% beat --loglevel=INFO
)
exit /b %ERRORLEVEL%

:usage
echo 用法: run-celery.cmd ^<profile^> ^<worker^|beat^> >&2
echo   profile  环境名，对应 backend\.env.^<profile^> >&2
echo   子命令   worker 或 beat（须同时跑两者时请各执行一次） >&2
echo. >&2
echo 示例: >&2
echo   run-celery.cmd local worker >&2
echo   run-celery.cmd local beat >&2
exit /b 1
