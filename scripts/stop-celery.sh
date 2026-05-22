#!/usr/bin/env bash
set -euo pipefail
echo "Stopping Celery processes matching app.celery_app..."
pkill -f "celery -A app.celery_app" 2>/dev/null || true
echo "Done."
