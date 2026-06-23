#!/usr/bin/env bash
# 在仓库根目录执行：启动 Vite 前端
# Usage:
#   run-frontend.sh [start|stop|status|restart]   默认前台；start 为 nohup 后台
# 局域网：Vite 监听所有网卡；其它设备用终端 Network 地址访问（需后端 run-backend 与按需 run-celery 已启动）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UI_DIR="${REPO_ROOT}/frontend"
PORT="${MINERVA_FRONTEND_PORT:-}"

# shellcheck source=_service-common.sh
source "${SCRIPT_DIR}/_service-common.sh"

usage() {
  cat >&2 <<'EOF'
Usage: run-frontend.sh [start|stop|status|restart]

  start     nohup background; pid/log under .minerva/
  stop      stop background dev server
  status    show running state
  restart   stop then start in background

Env: MINERVA_FRONTEND_PORT (optional, default Vite 5173)
EOF
}

ACTION="foreground"
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "start" || "${1:-}" == "stop" || "${1:-}" == "status" || "${1:-}" == "restart" ]]; then
  ACTION="$1"
  shift
fi

if [[ ! -d "${UI_DIR}/node_modules" ]]; then
  echo "未检测到 node_modules，正在执行 npm install..."
  (cd "${UI_DIR}" && npm install)
fi

SERVICE_NAME="frontend"
if [[ -n "${PORT}" ]]; then
  SERVICE_NAME="frontend-${PORT}"
fi

NPM_CMD=()

build_npm_cmd() {
  if [[ -n "${PORT}" ]]; then
    NPM_CMD=(npm run dev -- --host 0.0.0.0 --port "${PORT}")
    echo "目录: ${UI_DIR}  端口: ${PORT}"
  else
    NPM_CMD=(npm run dev -- --host 0.0.0.0)
    echo "目录: ${UI_DIR}（Vite 默认端口 5173）"
  fi
}

case "${ACTION}" in
  foreground)
    cd "${UI_DIR}"
    build_npm_cmd
    exec "${NPM_CMD[@]}"
    ;;
  start)
    build_npm_cmd
    cd "${UI_DIR}"
    minerva_service_start "${SERVICE_NAME}" "${NPM_CMD[@]}"
    ;;
  stop)
    minerva_service_stop "${SERVICE_NAME}"
    ;;
  status)
    minerva_service_status "${SERVICE_NAME}"
    ;;
  restart)
    build_npm_cmd
    cd "${UI_DIR}"
    minerva_service_restart "${SERVICE_NAME}" "${NPM_CMD[@]}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
