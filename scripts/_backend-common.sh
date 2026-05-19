#!/usr/bin/env bash
# 被 run-backend.sh / run-celery.sh source；勿直接执行。
# 用法: minerva_backend_setup <profile>
# 设置: MINERVA_BACKEND_DIR, MINERVA_PYTHON, APP_ENV；失败时 exit 1

minerva_backend_setup() {
  local profile="${1:?profile required}"
  local script_dir repo_root backend_dir env_file

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "${script_dir}/.." && pwd)"
  backend_dir="${repo_root}/backend"
  env_file="${backend_dir}/.env.${profile}"

  export APP_ENV="${profile}"
  export MINERVA_BACKEND_DIR="${backend_dir}"

  if [[ ! -f "${env_file}" ]]; then
    echo "错误: 未找到环境文件 ${env_file}" >&2
    echo "提示: cp backend/.env.example backend/.env.${profile}" >&2
    exit 1
  fi

  if [[ -f "${backend_dir}/.venv/bin/python" ]]; then
    MINERVA_PYTHON="${backend_dir}/.venv/bin/python"
  elif [[ -f "${backend_dir}/minerva/Scripts/python.exe" ]]; then
    MINERVA_PYTHON="${backend_dir}/minerva/Scripts/python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    MINERVA_PYTHON="python3"
  elif command -v python >/dev/null 2>&1; then
    MINERVA_PYTHON="python"
  else
    echo "错误: 未找到 python3 或 python，请安装 Python 3.11+ 或在 backend/.venv 创建虚拟环境。" >&2
    exit 1
  fi
  export MINERVA_PYTHON

  cd "${backend_dir}" || exit 1
  echo "环境: APP_ENV=${APP_ENV}  文件: ${env_file}"
  echo "Python: ${MINERVA_PYTHON}"
}
