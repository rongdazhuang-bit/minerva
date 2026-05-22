"""CLI entry: verify Celery broker Redis before starting worker/beat."""

from __future__ import annotations

import os
import sys

from app.sys.celery.service.redis_connection import verify_celery_broker_reachable


def main() -> int:
    """Exit 0 when broker responds to PING; 1 with stderr guidance otherwise."""

    if os.environ.get("CELERY_SKIP_BROKER_PREFLIGHT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return 0
    ok, message = verify_celery_broker_reachable()
    if ok:
        print(message)
        return 0
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
