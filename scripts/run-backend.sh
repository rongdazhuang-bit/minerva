#!/usr/bin/env bash
# Start FastAPI (uvicorn). Usage: run-backend.sh [profile]  default local
# Default Python: backend/.venv/bin/python (or Scripts/python.exe on Windows Git Bash)
# Env: MINERVA_BACKEND_PORT, MINERVA_PYTHON, MINERVA_ALLOW_SYSTEM_PYTHON
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"

# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"

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

echo "[run-backend] dir: ${MINERVA_BACKEND_DIR}  port: ${PORT}"
exec "${MINERVA_PYTHON}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT}"
