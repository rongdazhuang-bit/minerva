#!/usr/bin/env bash
# 在仓库根目录执行：启动 FastAPI 后端（默认 http://0.0.0.0:8000 ）
# 环境变量：APP_ENV、MINERVA_BACKEND_PORT（覆盖端口，默认 8000）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
PORT="${MINERVA_BACKEND_PORT:-8000}"

cd "${BACKEND_DIR}"

PYTHON="python3"
if [[ -f "${BACKEND_DIR}/.venv/bin/python" ]]; then
  PYTHON="${BACKEND_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "错误: 未找到 python3 或 python，请安装 Python 3.11+ 或在 backend/.venv 创建虚拟环境。" >&2
  exit 1
fi

echo "使用: ${PYTHON}"
echo "目录: ${BACKEND_DIR}  端口: ${PORT}"
exec "${PYTHON}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT}"
