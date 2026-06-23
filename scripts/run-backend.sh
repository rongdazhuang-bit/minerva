#!/usr/bin/env bash
# Start FastAPI (uvicorn).
# Usage:
#   run-backend.sh [profile]              foreground (default local)
#   run-backend.sh start [profile]        nohup background (Linux/macOS)
#   run-backend.sh stop|status|restart [profile]
# Env: MINERVA_BACKEND_PORT, MINERVA_PYTHON, MINERVA_ALLOW_SYSTEM_PYTHON, MINERVA_BACKEND_RELOAD
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"

# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"
# shellcheck source=_service-common.sh
source "${SCRIPT_DIR}/_service-common.sh"

usage() {
  cat >&2 <<'EOF'
Usage: run-backend.sh [start|stop|status|restart] [profile]

  profile   env name -> backend/.env.<profile>  (default: local)
  start     nohup background; pid/log under .minerva/
  stop      stop background service for profile
  status    show running state
  restart   stop then start in background

Examples:
  run-backend.sh
  run-backend.sh dev
  run-backend.sh start local
  run-backend.sh stop local
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
PROFILE="${1:-local}"

PORT="${MINERVA_BACKEND_PORT:-8000}"

if [[ -z "${MINERVA_PYTHON:-}" ]]; then
  if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    export MINERVA_PYTHON="${BACKEND_DIR}/.venv/bin/python"
  elif [[ -f "${BACKEND_DIR}/.venv/Scripts/python.exe" ]]; then
    export MINERVA_PYTHON="${BACKEND_DIR}/.venv/Scripts/python.exe"
  fi
fi

minerva_backend_setup "${PROFILE}"

SERVICE_NAME="backend-${PROFILE}"
UVICORN_ARGS=(--host 0.0.0.0 --port "${PORT}")
if [[ "${ACTION}" == "foreground" || "${MINERVA_BACKEND_RELOAD:-}" == "1" ]]; then
  UVICORN_ARGS+=(--reload)
fi

run_uvicorn() {
  exec "${MINERVA_PYTHON}" -m uvicorn app.main:app "${UVICORN_ARGS[@]}"
}

case "${ACTION}" in
  foreground)
    echo "[run-backend] dir: ${MINERVA_BACKEND_DIR}  port: ${PORT}"
    run_uvicorn
    ;;
  start)
    echo "[run-backend] dir: ${MINERVA_BACKEND_DIR}  port: ${PORT}"
    minerva_service_start "${SERVICE_NAME}" \
      "${MINERVA_PYTHON}" -m uvicorn app.main:app "${UVICORN_ARGS[@]}"
    ;;
  stop)
    minerva_service_stop "${SERVICE_NAME}"
    ;;
  status)
    minerva_service_status "${SERVICE_NAME}"
    ;;
  restart)
    echo "[run-backend] dir: ${MINERVA_BACKEND_DIR}  port: ${PORT}"
    minerva_service_restart "${SERVICE_NAME}" \
      "${MINERVA_PYTHON}" -m uvicorn app.main:app "${UVICORN_ARGS[@]}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
