#!/usr/bin/env bash
# Sourced by run-backend.sh / run-celery.sh. Do not execute directly.
# Usage: minerva_backend_setup <profile>
# Sets MINERVA_BACKEND_DIR, MINERVA_PYTHON (backend/.venv by default), APP_ENV
# Creates backend/.venv when missing and installs -e '.[dev]' when deps are incomplete.

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

minerva_backend_deps_installed() {
  local pip_py=$1

  "${pip_py}" -c "import uvicorn" >/dev/null 2>&1
}

minerva_install_spacy_model_if_needed() {
  local pip_py=$1

  if [[ "${MINERVA_SKIP_SPACY_MODEL:-}" == "1" ]]; then
    return 0
  fi
  if ! "${pip_py}" -c "import spacy" >/dev/null 2>&1; then
    return 0
  fi
  if "${pip_py}" -c "import en_core_web_sm" >/dev/null 2>&1; then
    return 0
  fi

  echo "[venv] downloading spaCy model en_core_web_sm (mem0 NLP)..."
  if ! "${pip_py}" -m spacy download en_core_web_sm; then
    echo "[warn] spaCy model en_core_web_sm download failed; mem0 NLP may be unavailable" >&2
    echo "[hint] retry: ${pip_py} -m spacy download en_core_web_sm" >&2
    echo "[hint] or set MINERVA_SKIP_SPACY_MODEL=1 if using AGENT_MEMORY_BACKEND=sql only" >&2
  fi
}

minerva_install_backend_deps() {
  local backend_dir=$1
  local pip_py=$2

  if [[ ! -f "${backend_dir}/pyproject.toml" ]]; then
    echo "[error] ${backend_dir}/pyproject.toml not found; cannot install backend deps" >&2
    return 1
  fi

  echo "[venv] upgrading pip..."
  "${pip_py}" -m pip install -U pip wheel

  echo "[venv] installing backend editable dependencies (.[dev])..."
  (
    cd "${backend_dir}" || exit 1
    "${pip_py}" -m pip install -e '.[dev]'
  )

  minerva_install_spacy_model_if_needed "${pip_py}"

  if ! minerva_backend_deps_installed "${pip_py}"; then
    echo "[error] backend dependencies still missing after pip install (uvicorn not importable)" >&2
    return 1
  fi

  echo "[venv] dependencies ready"
  return 0
}

minerva_bootstrap_backend_venv() {
  local backend_dir=$1
  local venv_dir="${backend_dir}/.venv"
  local pip_py bootstrap

  if [[ "${MINERVA_SKIP_VENV_BOOTSTRAP:-}" == "1" ]]; then
    return 1
  fi

  if pip_py="$(minerva_backend_venv_python "${backend_dir}")"; then
    if minerva_backend_deps_installed "${pip_py}"; then
      return 0
    fi
    echo "[venv] backend/.venv exists but dependencies are incomplete; installing..."
    minerva_install_backend_deps "${backend_dir}" "${pip_py}"
    return $?
  fi

  if ! bootstrap="$(minerva_find_bootstrap_python)"; then
    echo "[error] python3/python with stdlib venv not found; cannot create backend/.venv" >&2
    return 1
  fi

  echo "[venv] backend/.venv not found; creating with ${bootstrap}..."
  "${bootstrap}" -m venv "${venv_dir}"

  if ! pip_py="$(minerva_backend_venv_python "${backend_dir}")"; then
    echo "[error] venv created but python executable is missing under ${venv_dir}" >&2
    return 1
  fi

  minerva_install_backend_deps "${backend_dir}" "${pip_py}"
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
    if [[ "${MINERVA_PYTHON}" == "${venv_py}" || "${MINERVA_PYTHON}" == "${venv_py_win}" ]]; then
      if ! minerva_backend_deps_installed "${MINERVA_PYTHON}"; then
        minerva_install_backend_deps "${backend_dir}" "${MINERVA_PYTHON}" || exit 1
      fi
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
  elif minerva_bootstrap_backend_venv "${backend_dir}"; then
    if pip_py="$(minerva_backend_venv_python "${backend_dir}")"; then
      MINERVA_PYTHON="${pip_py}"
    elif [[ -f "${venv_py}" && -x "${venv_py}" ]]; then
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
