#!/usr/bin/env bash
# 启动 Celery Worker 或 Beat。用法: run-celery.sh <profile> <worker|beat>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_backend-common.sh
source "${SCRIPT_DIR}/_backend-common.sh"

usage() {
  cat >&2 <<'EOF'
用法: run-celery.sh <profile> <worker|beat>
  profile  环境名，对应 backend/.env.<profile>
  子命令   worker 或 beat（须同时跑两者时请各执行一次）

示例:
  run-celery.sh local worker
  run-celery.sh local beat
  run-celery.sh dev worker
EOF
}

if [[ $# -ne 2 ]]; then
  usage
  exit 1
fi

PROFILE="$1"
SUBCMD="$2"

case "${SUBCMD}" in
  worker|beat) ;;
  *)
    echo "错误: 子命令必须是 worker 或 beat，收到: ${SUBCMD}" >&2
    usage
    exit 1
    ;;
esac

minerva_backend_setup "${PROFILE}"

CELERY_APP="app.celery_app:celery_app"
"${MINERVA_PYTHON}" -m app.sys.celery.service.broker_preflight
if [[ "${SUBCMD}" == "worker" ]]; then
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" worker --loglevel=INFO
else
  exec "${MINERVA_PYTHON}" -m celery -A "${CELERY_APP}" beat --loglevel=INFO
fi
