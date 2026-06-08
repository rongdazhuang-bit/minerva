#!/usr/bin/env bash
# Start Celery worker or beat. Usage: run-celery.sh <profile> <worker|beat>
# Default Python: backend/.venv/bin/python (or Scripts/python.exe on Windows Git Bash)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"

# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"

usage() {
  cat >&2 <<'EOF'
Usage: run-celery.sh <profile> <worker|beat>
  profile   env name, maps to backend/.env.<profile>
  subcmd    worker or beat (run twice for both)

Examples:
  run-celery.sh local worker
  run-celery.sh local beat
EOF
}

if [[ $# -ne 2 ]]; then
  usage
  exit 1
fi

PROFILE="$1"
SUBCMD="$2"

case "${SUBCMD}" in
  worker|beat) ;;
  *)
    echo "[error] subcommand must be worker or beat, got: ${SUBCMD}" >&2
    usage
    exit 1
    ;;
esac

if [[ -z "${MINERVA_PYTHON:-}" ]]; then
  if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    export MINERVA_PYTHON="${BACKEND_DIR}/.venv/bin/python"
  elif [[ -f "${BACKEND_DIR}/.venv/Scripts/python.exe" ]]; then
    export MINERVA_PYTHON="${BACKEND_DIR}/.venv/Scripts/python.exe"
  fi
fi

minerva_backend_setup "${PROFILE}"

CELERY_APP="app.celery_app:celery_app"
"${MINERVA_PYTHON}" -m app.sys.celery.service.broker_preflight
export MINERVA_CELERY_POOL="${MINERVA_CELERY_POOL:-}"
export MINERVA_CELERY_CONCURRENCY="${MINERVA_CELERY_CONCURRENCY:-4}"
export MINERVA_CELERY_QUEUES="${MINERVA_CELERY_QUEUES:-default,dataset}"
if [[ "${SUBCMD}" == "worker" ]]; then
  POOL="${MINERVA_CELERY_POOL}"
  if [[ -z "${POOL}" ]]; then
    if [[ "$(uname -s 2>/dev/null || true)" == *MINGW* ]] || [[ "$(uname -s 2>/dev/null || true)" == *MSYS* ]]; then
      POOL="threads"
    else
      POOL="prefork"
    fi
  fi
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" worker --loglevel=INFO \
    --pool="${POOL}" --concurrency="${MINERVA_CELERY_CONCURRENCY}" -Q "${MINERVA_CELERY_QUEUES}"
else
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" beat --loglevel=INFO
fi
