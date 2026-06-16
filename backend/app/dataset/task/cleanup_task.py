"""Celery task for async dataset external resource cleanup."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from celery import Task, shared_task

from app.core.infrastructure.db.session import async_session_factory, engine
from app.core.log import get_logger
from app.dataset.domain.constants import DATASET_CLEANUP_TASK_NAME
from app.dataset.service.cleanup_service import run_dataset_cleanup

log = get_logger(__name__)


def _run_async(manifest: dict[str, Any]) -> dict[str, Any]:
    """Run cleanup on a dedicated event loop."""

    async def _runner() -> dict[str, Any]:
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_dataset_cleanup(session, manifest)
        finally:
            await engine.dispose(close=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_runner())


@shared_task(bind=True, name=DATASET_CLEANUP_TASK_NAME)
def dataset_cleanup_task(self: Task, manifest: dict[str, Any]) -> dict[str, Any]:
    """Delete S3 uploads and vector collection after dataset SQL rows are gone."""

    log.info(
        "dataset.cleanup start dataset_id={} upload_count={} task_id={}",
        manifest.get("dataset_id"),
        len(manifest.get("uploads") or []),
        getattr(self.request, "id", None),
    )
    summary = _run_async(manifest)
    log.info("dataset.cleanup done summary={}", summary)
    return summary
