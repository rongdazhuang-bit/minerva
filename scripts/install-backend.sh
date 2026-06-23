#!/usr/bin/env bash
# Install backend Python dependencies into backend/.venv (not run by run-backend / run-celery).
# Usage: install-backend.sh
# Env: MINERVA_SKIP_SPACY_MODEL=1 to skip spaCy model download after pip install
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"

# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"

if [[ "${MINERVA_SKIP_VENV_BOOTSTRAP:-}" != "1" ]]; then
  minerva_create_backend_venv_if_missing "${BACKEND_DIR}" || exit 1
fi

if ! PIP_PY="$(minerva_backend_venv_python "${BACKEND_DIR}")"; then
  echo "[error] backend/.venv not found; run without MINERVA_SKIP_VENV_BOOTSTRAP or create venv manually" >&2
  exit 1
fi

if [[ ! -f "${BACKEND_DIR}/pyproject.toml" ]]; then
  echo "[error] ${BACKEND_DIR}/pyproject.toml not found" >&2
  exit 1
fi

echo "[install-backend] python: ${PIP_PY}"
echo "[install-backend] upgrading pip..."
"${PIP_PY}" -m pip install -U pip wheel

echo "[install-backend] installing editable package (.[dev])..."
(
  cd "${BACKEND_DIR}"
  "${PIP_PY}" -m pip install -e '.[dev]'
)

if [[ "${MINERVA_SKIP_SPACY_MODEL:-}" != "1" ]] && "${PIP_PY}" -c "import spacy" >/dev/null 2>&1; then
  if ! "${PIP_PY}" -c "import en_core_web_sm" >/dev/null 2>&1; then
    echo "[install-backend] downloading spaCy model en_core_web_sm..."
    "${PIP_PY}" -m spacy download en_core_web_sm || {
      echo "[warn] spaCy model download failed; mem0 NLP may be unavailable" >&2
    }
  fi
fi

minerva_assert_backend_deps "${PIP_PY}" "${BACKEND_DIR}" || exit 1
echo "[install-backend] done"
