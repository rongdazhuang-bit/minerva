#!/usr/bin/env bash
# Sourced by run-backend.sh / run-celery.sh. Do not execute directly.
# Usage: minerva_backend_setup <profile>
# Sets MINERVA_BACKEND_DIR, MINERVA_PYTHON (backend/.venv by default), APP_ENV
# When backend/.venv is missing, creates it and runs pip install -e '.[dev]' (unless MINERVA_SKIP_VENV_BOOTSTRAP=1).

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

minerva_backend_venv_ready() {
  local backend_dir=$1
  local venv_py="${backend_dir}/.venv/bin/python"
  local venv_py_win="${backend_dir}/.venv/Scripts/python.exe"

  [[ -f "${venv_py}" && -x "${venv_py}" ]] && return 0
  [[ -f "${venv_py_win}" ]] && return 0
  return 1
}

minerva_ensure_backend_venv() {
  local backend_dir=$1
  local venv_dir="${backend_dir}/.venv"
  local venv_py="${backend_dir}/.venv/bin/python"
  local bootstrap

  if minerva_backend_venv_ready "${backend_dir}"; then
    return 0
  fi
  if [[ "${MINERVA_SKIP_VENV_BOOTSTRAP:-}" == "1" ]]; then
    return 1
  fi
  if [[ ! -f "${backend_dir}/pyproject.toml" ]]; then
    echo "[error] ${backend_dir}/pyproject.toml not found; cannot bootstrap venv" >&2
    return 1
  fi
  if ! bootstrap="$(minerva_find_bootstrap_python)"; then
    echo "[error] python3/python with stdlib venv not found; cannot create backend/.venv" >&2
    return 1
  fi

  echo "[venv] backend/.venv not found; creating with ${bootstrap}..."
  "${bootstrap}" -m venv "${venv_dir}"

  if [[ ! -f "${venv_py}" && ! -f "${backend_dir}/.venv/Scripts/python.exe" ]]; then
    echo "[error] venv created but python executable is missing under ${venv_dir}" >&2
    return 1
  fi

  local pip_py="${venv_py}"
  if [[ ! -x "${pip_py}" ]]; then
    pip_py="${backend_dir}/.venv/Scripts/python.exe"
  fi

  echo "[venv] upgrading pip..."
  "${pip_py}" -m pip install -U pip wheel

  echo "[venv] installing backend editable dependencies (.[dev])..."
  (
    cd "${backend_dir}" || exit 1
    "${pip_py}" -m pip install -e '.[dev]'
  )

  if ! minerva_backend_venv_ready "${backend_dir}"; then
    echo "[error] venv bootstrap finished but backend/.venv python is still unavailable" >&2
    return 1
  fi

  echo "[venv] ready"
  return 0
}

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
  elif minerva_ensure_backend_venv "${backend_dir}"; then
    if [[ -f "${venv_py}" && -x "${venv_py}" ]]; then
      MINERVA_PYTHON="${venv_py}"
    elif [[ -f "${venv_py_win}" ]]; then
      MINERVA_PYTHON="${venv_py_win}"
    else
      echo "[error] backend/.venv bootstrap succeeded but python path is unknown" >&2
      exit 1
    fi
  else
    echo "[error] backend/.venv not found (expected ${venv_py})" >&2
    echo "[hint] cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    echo "[hint] or export MINERVA_ALLOW_SYSTEM_PYTHON=1 to use system Python" >&2
    echo "[hint] or export MINERVA_SKIP_VENV_BOOTSTRAP=1 to disable auto bootstrap" >&2
    exit 1
  fi
  export MINERVA_PYTHON

  cd "${backend_dir}" || exit 1
  echo "[env] APP_ENV=${APP_ENV}  file=${env_file}"
  echo "[python] ${MINERVA_PYTHON}"
}
