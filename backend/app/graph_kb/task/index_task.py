"""Celery task entry for GraphKB document indexing."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from celery import Task, shared_task

from app.core.infrastructure.db.session import async_session_factory, engine
from app.core.log import get_logger
from app.graph_kb.domain.constants import GRAPH_KB_INDEX_TASK_NAME
from app.graph_kb.service.index_service import run_index_job

log = get_logger(__name__)


def _run_async(job_id: str) -> dict[str, Any]:
    """Run one index job on a dedicated event loop."""

    async def _runner() -> dict[str, Any]:
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_index_job(session, job_id=uuid.UUID(job_id))
        finally:
            await engine.dispose(close=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_runner())


@shared_task(bind=True, name=GRAPH_KB_INDEX_TASK_NAME, queue="graph_kb")
def graph_kb_index_task(self: Task, job_id: str) -> dict[str, Any]:
    """Index one GraphKB job asynchronously on queue ``graph_kb``."""

    log.info(
        "graph_kb.indexing start job_id={} task_id={}",
        job_id,
        getattr(self.request, "id", None),
    )
    summary = _run_async(job_id)
    log.info("graph_kb.indexing done summary={}", summary)
    return summary
