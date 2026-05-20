"""Celery task entry for one document translation job."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from celery import Task, shared_task
from celery.utils.log import get_task_logger

from app.core.infrastructure.db.session import async_session_factory, engine
from app.translate.domain.constants import DOC_TRANSLATE_RUN_TASK_NAME
from app.translate.service.run_pipeline import run_job_once

logger = get_task_logger(__name__)


def _run_async(job_id: str) -> dict[str, Any]:
    """Run pipeline on a dedicated event loop (same pattern as file_ocr scan_init)."""

    async def _runner() -> dict[str, Any]:
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_job_once(session, uuid.UUID(job_id))
        finally:
            await engine.dispose(close=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_runner())


@shared_task(bind=True, name=DOC_TRANSLATE_RUN_TASK_NAME)
def run_doc_translate_job(self: Task, job_id: str) -> dict[str, Any]:
    """Process one ``doc_translate_job`` through extract, translate, and assemble."""

    logger.info("translate.run_job start job_id=%s task_id=%s", job_id, getattr(self.request, "id", None))
    summary = _run_async(job_id)
    logger.info("translate.run_job done summary=%s", summary)
    return summary
