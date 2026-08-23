#!/usr/bin/env bash
# Install isolated GraphKB engine workers (LightRAG + GraphRAG) into workers/*/.venv.
# Usage: bash scripts/install-graph-kb-workers.sh
# Env: MINERVA_SKIP_VENV_BOOTSTRAP=1 to fail instead of creating missing venvs
#      MINERVA_GRAPH_KB_WORKERS=lightrag,graphrag  (default: both)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

minerva_find_bootstrap_python() {
  local candidate
  for candidate in python3.13 python3.12 python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      if "${candidate}" -c "import venv" >/dev/null 2>&1; then
        echo "${candidate}"
        return 0
      fi
    fi
  done
  return 1
}

minerva_worker_venv_python() {
  local worker_dir=$1
  local venv_py="${worker_dir}/.venv/bin/python"
  local venv_py_win="${worker_dir}/.venv/Scripts/python.exe"
  if [[ -f "${venv_py}" && -x "${venv_py}" ]]; then
    echo "${venv_py}"
    return 0
  fi
  if [[ -f "${venv_py_win}" ]]; then
    echo "${venv_py_win}"
    return 0
  fi
  return 1
}

minerva_create_worker_venv_if_missing() {
  local worker_dir=$1
  local bootstrap
  if minerva_worker_venv_python "${worker_dir}" >/dev/null; then
    return 0
  fi
  if [[ "${MINERVA_SKIP_VENV_BOOTSTRAP:-}" == "1" ]]; then
    echo "[error] ${worker_dir}/.venv not found" >&2
    return 1
  fi
  if ! bootstrap="$(minerva_find_bootstrap_python)"; then
    echo "[error] python with stdlib venv not found; cannot create ${worker_dir}/.venv" >&2
    return 1
  fi
  echo "[venv] creating ${worker_dir}/.venv with ${bootstrap}..."
  "${bootstrap}" -m venv "${worker_dir}/.venv"
  minerva_worker_venv_python "${worker_dir}" >/dev/null
}

minerva_install_worker() {
  local name=$1
  local worker_dir="${REPO_ROOT}/workers/graph-kb-${name}"
  local pip_py

  if [[ ! -f "${worker_dir}/pyproject.toml" ]]; then
    echo "[error] missing ${worker_dir}/pyproject.toml" >&2
    return 1
  fi
  minerva_create_worker_venv_if_missing "${worker_dir}" || return 1
  pip_py="$(minerva_worker_venv_python "${worker_dir}")"
  echo "[install-graph-kb-workers] ${name}: ${pip_py}"
  "${pip_py}" -m pip install -U pip wheel
  (
    cd "${worker_dir}"
    "${pip_py}" -m pip install -e '.[dev,engine]'
  )
  if [[ "${name}" == "lightrag" ]]; then
    "${pip_py}" -c "import lightrag; import asyncpg; import pgvector" >/dev/null
  else
    "${pip_py}" -c "import graphrag; import pandas; import pyarrow" >/dev/null
  fi
  echo "[install-graph-kb-workers] ${name}: engine import OK"
}

IFS=',' read -r -a TARGETS <<< "${MINERVA_GRAPH_KB_WORKERS:-lightrag,graphrag}"
for target in "${TARGETS[@]}"; do
  target="$(echo "${target}" | xargs)"
  case "${target}" in
    lightrag|graphrag) minerva_install_worker "${target}" ;;
    *)
      echo "[error] unknown worker '${target}' (use lightrag or graphrag)" >&2
      exit 1
      ;;
  esac
done

echo "[install-graph-kb-workers] done"
