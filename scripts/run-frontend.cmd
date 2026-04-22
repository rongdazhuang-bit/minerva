@echo off
setlocal EnableExtensions
REM 在仓库根目录启动 Vite 前端。可选: set MINERVA_FRONTEND_PORT=3000

set "UI=%~dp0..\minerva-ui"

cd /d "%UI%" || exit /b 1

if not exist "node_modules\" (
  echo 未检测到 node_modules，正在执行 npm install...
  call npm install || exit /b 1
)

if defined MINERVA_FRONTEND_PORT (
  echo 目录: %UI%  端口: %MINERVA_FRONTEND_PORT%
  call npm run dev -- --port %MINERVA_FRONTEND_PORT%
) else (
  echo 目录: %UI%（默认 5173）
  call npm run dev
)
exit /b %ERRORLEVEL%
