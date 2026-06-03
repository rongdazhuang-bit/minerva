"""Celery task that runs one bounded pass over INIT ``ocr_file`` rows."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from celery import Task, shared_task

from app.core.infrastructure.db.session import async_session_factory
from app.core.infrastructure.db.session import engine
from app.core.log import get_logger
from app.file_ocr.constants import FILE_OCR_SCAN_INIT_TASK_NAME
from app.file_ocr.service.scan_init import run_file_ocr_scan_tick

log = get_logger(__name__)


def _run_async_scan_tick() -> dict[str, Any]:
    """
    Run one DB-backed scan tick on a dedicated short-lived event loop.

    Celery workers are synchronous; ``asyncio.run`` supplies the loop asyncpg needs.
    On Windows the default Proactor loop plus ``asyncio.run`` teardown can leave the
    process-global async engine pool with connections tied to a closed loop; this
    wrapper disposes the pool while the loop is still alive and prefers the selector
    policy to avoid broken IOCP shutdown during pool ping/checkout.
    """

    async def _runner() -> dict[str, Any]:
        """Open a session, run the tick, then drop pooled connections before the loop closes."""
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_file_ocr_scan_tick(session)
        finally:
            await engine.dispose(close=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_runner())


@shared_task(bind=True, name=FILE_OCR_SCAN_INIT_TASK_NAME)
def scan_init_ocr_files(self: Task, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Drain a bounded batch of INIT Paddle tasks and persist OCR output rows.

    Beat schedules built from ``sys_celery`` may supply ``args_json`` / ``kwargs_json``
    (for example ``source`` for audit); extra positional or keyword arguments are ignored.
    """

    log.info("file_ocr.scan_init start task_id={}", getattr(self.request, "id", None))
    summary = _run_async_scan_tick()
    log.info("file_ocr.scan_init done summary={}", summary)
    return summary
