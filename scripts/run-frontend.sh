#!/usr/bin/env bash
# 在仓库根目录执行：启动 Vite 前端
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UI_DIR="${REPO_ROOT}/minerva-ui"
PORT="${MINERVA_FRONTEND_PORT:-}"

cd "${UI_DIR}"

if [[ ! -d node_modules ]]; then
  echo "未检测到 node_modules，正在执行 npm install..."
  npm install
fi

if [[ -n "${PORT}" ]]; then
  echo "目录: ${UI_DIR}  端口: ${PORT}"
  exec npm run dev -- --port "${PORT}"
else
  echo "目录: ${UI_DIR}（Vite 默认端口 5173）"
  exec npm run dev
fi
