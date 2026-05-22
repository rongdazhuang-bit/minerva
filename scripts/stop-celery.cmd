@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM 结束本机 Minerva Celery Worker/Beat 进程（Ctrl+C 无效时使用）。

echo 正在结束 Celery 相关进程...
taskkill /F /T /FI "IMAGENAME eq celery.exe" 2>nul
if errorlevel 1 (
  echo 未发现 celery.exe 进程。
) else (
  echo 已发送 taskkill 至 celery.exe 进程树。
)

for /f "tokens=1" %%p in ('wmic process where "CommandLine like '%%celery -A app.celery_app%%'" get ProcessId 2^>nul ^| findstr /r "[0-9]"') do (
  taskkill /F /PID %%p 2>nul
)

echo 完成。若仍有残留，请在任务管理器中结束对应 python.exe。
exit /b 0
