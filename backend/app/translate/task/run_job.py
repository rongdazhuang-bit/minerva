"""Celery task entry for one document translation job."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from celery import Task, shared_task

from app.core.infrastructure.db.session import async_session_factory, engine
from app.core.log import get_logger
from app.sys.celery.service.task_schedule_validation import resolve_doc_translate_job_id
from app.translate.domain.constants import DOC_TRANSLATE_RUN_TASK_NAME
from app.translate.service.run_pipeline import run_job_once

log = get_logger(__name__)


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
def run_doc_translate_job(self: Task, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Process one ``doc_translate_job`` through extract, translate, and assemble.

    Beat schedules from ``sys_celery`` may include audit kwargs (e.g. ``source``); only
    ``job_id`` (first positional arg or ``kwargs['job_id']``) is used. Upload API enqueue
    passes ``job_id`` as the sole positional argument.
    """

    job_id = resolve_doc_translate_job_id(args, kwargs)
    if not job_id:
        log.warn(
            "translate.run_job skipped: valid UUID job_id required task_id={} args={} kwargs_keys={}",
            getattr(self.request, "id", None),
            list(args),
            sorted(kwargs.keys()),
        )
        return {"ok": False, "reason": "job_id_invalid_or_missing"}

    log.info("translate.run_job start job_id={} task_id={}", job_id, getattr(self.request, "id", None))
    summary = _run_async(job_id)
    log.info("translate.run_job done summary={}", summary)
    return summary
