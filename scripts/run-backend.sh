#!/usr/bin/env bash
# 在仓库根目录执行：启动 FastAPI 后端（默认 http://0.0.0.0:8000 ）；可选后台启动 Celery Worker
# 环境变量：APP_ENV、MINERVA_BACKEND_PORT（覆盖端口，默认 8000）
# 可选：MINERVA_SKIP_CELERY_WORKER=1 跳过 Worker；MINERVA_SKIP_CELERY_BEAT=1 跳过 Beat（定时调度依赖 Beat）。
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

CELERY_PID=""
BEAT_PID=""
cleanup() {
  if [[ -n "${BEAT_PID}" ]] && kill -0 "${BEAT_PID}" 2>/dev/null; then
    kill "${BEAT_PID}" 2>/dev/null || true
    wait "${BEAT_PID}" 2>/dev/null || true
  fi
  if [[ -n "${CELERY_PID}" ]] && kill -0 "${CELERY_PID}" 2>/dev/null; then
    kill "${CELERY_PID}" 2>/dev/null || true
    wait "${CELERY_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "使用: ${PYTHON}"
echo "目录: ${BACKEND_DIR}  端口: ${PORT}"

if [[ "${MINERVA_SKIP_CELERY_WORKER:-}" != "1" ]]; then
  "${PYTHON}" -m celery -A app.celery_app:celery_app worker --loglevel=INFO &
  CELERY_PID=$!
fi

if [[ "${MINERVA_SKIP_CELERY_BEAT:-}" != "1" ]]; then
  "${PYTHON}" -m celery -A app.celery_app:celery_app beat --loglevel=INFO &
  BEAT_PID=$!
fi

"${PYTHON}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT}"
