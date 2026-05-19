#!/usr/bin/env bash
# 启动 FastAPI（仅 uvicorn）。用法: run-backend.sh [profile]  默认 profile=local
# 环境变量: MINERVA_BACKEND_PORT（默认 8000）
# 局域网：监听 0.0.0.0；其它设备可访问 http://<本机IP>:端口（开发环境 CORS 含私网段）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"

PROFILE="${1:-local}"
PORT="${MINERVA_BACKEND_PORT:-8000}"

minerva_backend_setup "${PROFILE}"

echo "目录: ${MINERVA_BACKEND_DIR}  端口: ${PORT}"
exec "${MINERVA_PYTHON}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT}"
