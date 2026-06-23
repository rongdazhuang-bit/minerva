#!/usr/bin/env bash
# Sourced by run-backend.sh / run-celery.sh. Do not execute directly.
# Usage: minerva_backend_setup <profile>
# Sets MINERVA_BACKEND_DIR, MINERVA_PYTHON (backend/.venv by default), APP_ENV
# May create an empty backend/.venv when missing; does not run pip install (use install-backend.sh).

minerva_find_bootstrap_python() {
  local candidate

  for candidate in python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      if "${candidate}" -c "import venv" >/dev/null 2>&1; then
        echo "${candidate}"
        return 0
      fi
    fi
  done
  return 1
}

minerva_backend_venv_python() {
  local backend_dir=$1
  local venv_py="${backend_dir}/.venv/bin/python"
  local venv_py_win="${backend_dir}/.venv/Scripts/python.exe"

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

minerva_create_backend_venv_if_missing() {
  local backend_dir=$1
  local venv_dir="${backend_dir}/.venv"
  local bootstrap

  if minerva_backend_venv_python "${backend_dir}" >/dev/null; then
    return 0
  fi
  if [[ "${MINERVA_SKIP_VENV_BOOTSTRAP:-}" == "1" ]]; then
    return 1
  fi
  if ! bootstrap="$(minerva_find_bootstrap_python)"; then
    echo "[error] python3/python with stdlib venv not found; cannot create backend/.venv" >&2
    return 1
  fi

  echo "[venv] backend/.venv not found; creating empty venv with ${bootstrap}..."
  "${bootstrap}" -m venv "${venv_dir}"

  if minerva_backend_venv_python "${backend_dir}" >/dev/null; then
    echo "[venv] created; install deps: cd backend && .venv/bin/pip install -e '.[dev]'"
    echo "[hint] or run: bash scripts/install-backend.sh"
    return 0
  fi

  echo "[error] venv created but python executable is missing under ${venv_dir}" >&2
  return 1
}

minerva_assert_backend_deps() {
  local pip_py=$1
  local backend_dir=$2

  if "${pip_py}" -c "import uvicorn" >/dev/null 2>&1; then
    return 0
  fi

  echo "[error] backend dependencies not installed (uvicorn not importable)" >&2
  echo "[hint] cd ${backend_dir} && .venv/bin/pip install -e '.[dev]'" >&2
  echo "[hint] or run: bash scripts/install-backend.sh" >&2
  return 1
}

minerva_backend_setup() {
  local profile="${1:?profile required}"
  local script_dir repo_root backend_dir env_file
  local venv_py venv_py_win pip_py

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
  elif [[ "${MINERVA_ALLOW_SYSTEM_PYTHON:-}" == "1" ]]; then
    if command -v python3 >/dev/null 2>&1; then
      MINERVA_PYTHON="python3"
    elif command -v python >/dev/null 2>&1; then
      MINERVA_PYTHON="python"
    else
      echo "[error] python3/python not found on PATH" >&2
      exit 1
    fi
  elif minerva_create_backend_venv_if_missing "${backend_dir}" && pip_py="$(minerva_backend_venv_python "${backend_dir}")"; then
    MINERVA_PYTHON="${pip_py}"
  elif pip_py="$(minerva_backend_venv_python "${backend_dir}")"; then
    MINERVA_PYTHON="${pip_py}"
  else
    echo "[error] backend/.venv not found (expected ${venv_py})" >&2
    echo "[hint] bash scripts/install-backend.sh" >&2
    echo "[hint] or export MINERVA_ALLOW_SYSTEM_PYTHON=1 to use system Python" >&2
    echo "[hint] or export MINERVA_SKIP_VENV_BOOTSTRAP=1 to disable auto venv creation" >&2
    exit 1
  fi
  export MINERVA_PYTHON

  if [[ "${MINERVA_PYTHON}" == "${venv_py}" || "${MINERVA_PYTHON}" == "${venv_py_win}" ]]; then
    minerva_assert_backend_deps "${MINERVA_PYTHON}" "${backend_dir}" || exit 1
  fi

  cd "${backend_dir}" || exit 1
  echo "[env] APP_ENV=${APP_ENV}  file=${env_file}"
  echo "[python] ${MINERVA_PYTHON}"
}
