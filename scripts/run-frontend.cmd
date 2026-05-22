@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
REM Start Vite from minerva-ui. Optional: set MINERVA_FRONTEND_PORT=3000
REM LAN: Vite binds 0.0.0.0, use Network URL from terminal on other devices.
REM API proxy target: MINERVA_DEV_API_PROXY_TARGET (default http://127.0.0.1:8000)

set "UI=%~dp0..\minerva-ui"

cd /d "%UI%" || exit /b 1

if not exist "node_modules\" (
  echo [run-frontend] node_modules missing, running npm install...
  call npm install || exit /b 1
)

if defined MINERVA_FRONTEND_PORT (
  echo [run-frontend] dir: %UI%  port: %MINERVA_FRONTEND_PORT%
  call npm run dev -- --port %MINERVA_FRONTEND_PORT%
) else (
  echo [run-frontend] dir: %UI%  port: 5173 (default)
  call npm run dev
)
exit /b %ERRORLEVEL%
