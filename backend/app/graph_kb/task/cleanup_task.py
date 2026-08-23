"""Celery task entry for GraphKB namespace and object-store cleanup."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from celery import Task, shared_task

from app.core.infrastructure.db.session import async_session_factory, engine
from app.core.log import get_logger
from app.graph_kb.domain.constants import GRAPH_KB_CLEANUP_TASK_NAME
from app.graph_kb.service.cleanup_service import run_cleanup_job

log = get_logger(__name__)


def _run_async(workspace_id: str, graph_id: str, engine_name: str) -> dict[str, Any]:
    """Run cleanup on a dedicated event loop."""

    async def _runner() -> dict[str, Any]:
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_cleanup_job(
                    session,
                    workspace_id=uuid.UUID(workspace_id),
                    graph_id=uuid.UUID(graph_id),
                    engine=engine_name,
                )
        finally:
            await engine.dispose(close=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_runner())


@shared_task(bind=True, name=GRAPH_KB_CLEANUP_TASK_NAME, queue="graph_kb")
def graph_kb_cleanup_task(
    self: Task, workspace_id: str, graph_id: str, engine: str
) -> dict[str, Any]:
    """Delete Worker namespace and local files after graph SQL rows are gone."""

    log.info(
        "graph_kb.cleanup start graph_id={} engine={} task_id={}",
        graph_id,
        engine,
        getattr(self.request, "id", None),
    )
    summary = _run_async(workspace_id, graph_id, engine)
    log.info("graph_kb.cleanup done summary={}", summary)
    return summary
