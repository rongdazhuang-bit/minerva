#!/usr/bin/env bash
# Sourced by run-backend.sh / run-celery.sh. Do not execute directly.
# Usage: minerva_backend_setup <profile>
# Sets MINERVA_BACKEND_DIR, MINERVA_PYTHON (backend/.venv by default), APP_ENV

minerva_backend_setup() {
  local profile="${1:?profile required}"
  local script_dir repo_root backend_dir env_file
  local venv_py venv_py_win

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "${script_dir}/.." && pwd)"
  backend_dir="${MINERVA_BACKEND_DIR:-${repo_root}/backend}"
  env_file="${backend_dir}/.env.${profile}"
  venv_py="${backend_dir}/.venv/bin/python"
  venv_py_win="${backend_dir}/.venv/Scripts/python.exe"

  export APP_ENV="${profile}"
  export MINERVA_BACKEND_DIR="${backend_dir}"

  if [[ ! -f "${env_file}" ]]; then
    echo "[error] env file not found: ${env_file}" >&2
    echo "[hint] cp backend/.env.example backend/.env.${profile}" >&2
    exit 1
  fi

  if [[ -n "${MINERVA_PYTHON:-}" ]]; then
    if [[ ! -x "${MINERVA_PYTHON}" && ! -f "${MINERVA_PYTHON}" ]]; then
      echo "[error] MINERVA_PYTHON not found: ${MINERVA_PYTHON}" >&2
      exit 1
    fi
  elif [[ -f "${venv_py}" && -x "${venv_py}" ]]; then
    MINERVA_PYTHON="${venv_py}"
  elif [[ -f "${venv_py_win}" ]]; then
    MINERVA_PYTHON="${venv_py_win}"
  elif [[ "${MINERVA_ALLOW_SYSTEM_PYTHON:-}" == "1" ]]; then
    if command -v python3 >/dev/null 2>&1; then
      MINERVA_PYTHON="python3"
    elif command -v python >/dev/null 2>&1; then
      MINERVA_PYTHON="python"
    else
      echo "[error] python3/python not found on PATH" >&2
      exit 1
    fi
  else
    echo "[error] backend/.venv not found (expected ${venv_py})" >&2
    echo "[hint] cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    echo "[hint] or export MINERVA_ALLOW_SYSTEM_PYTHON=1 to use system Python" >&2
    exit 1
  fi
  export MINERVA_PYTHON

  cd "${backend_dir}" || exit 1
  echo "[env] APP_ENV=${APP_ENV}  file=${env_file}"
  echo "[python] ${MINERVA_PYTHON}"
}
