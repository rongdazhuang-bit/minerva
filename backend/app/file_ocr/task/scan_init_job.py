"""Celery task that runs one bounded pass over INIT ``ocr_file`` rows."""

from __future__ import annotations

import asyncio
from typing import Any

from celery import Task, shared_task
from celery.utils.log import get_task_logger

from app.core.infrastructure.db.session import async_session_factory
from app.file_ocr.constants import FILE_OCR_SCAN_INIT_TASK_NAME
from app.file_ocr.service.scan_init import run_file_ocr_scan_tick

logger = get_task_logger(__name__)


@shared_task(bind=True, name=FILE_OCR_SCAN_INIT_TASK_NAME)
def scan_init_ocr_files(self: Task) -> dict[str, Any]:
    """Drain a bounded batch of INIT Paddle tasks and persist OCR output rows."""

    async def _runner() -> dict[str, Any]:
        async with async_session_factory() as session:
            return await run_file_ocr_scan_tick(session)

    logger.info("file_ocr.scan_init start task_id=%s", getattr(self.request, "id", None))
    summary = asyncio.run(_runner())
    logger.info("file_ocr.scan_init done summary=%s", summary)
    return summary
