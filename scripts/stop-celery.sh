#!/usr/bin/env bash
# Stop Celery worker/beat started via run-celery.sh start (pid files) or legacy foreground processes.
# Usage: stop-celery.sh [profile]
#   profile   optional; when set, stops celery-worker-<profile> and celery-beat-<profile> only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=_service-common.sh
source "${SCRIPT_DIR}/_service-common.sh"

PROFILE="${1:-}"

if [[ -n "${PROFILE}" ]]; then
  echo "Stopping Celery services for profile: ${PROFILE}"
  minerva_service_stop "celery-worker-${PROFILE}"
  minerva_service_stop "celery-beat-${PROFILE}"
else
  echo "Stopping all Celery pid-file services..."
  minerva_service_stop_glob "celery-worker-*"
  minerva_service_stop_glob "celery-beat-*"
fi

echo "Stopping Celery processes matching app.celery_app..."
pkill -f "celery -A app.celery_app" 2>/dev/null || true
echo "Done."
