"""Enqueue and run GraphKB async cleanup (object store + Worker namespace)."""

from __future__ import annotations

import shutil
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.log import get_logger
from app.graph_kb.domain.constants import GRAPH_KB_CLEANUP_TASK_NAME
from app.graph_kb.engine.factory import create_engine_client
from app.graph_kb.infrastructure.pending_cleanup import (
    clear_pending_cleanup,
    iter_pending_cleanups,
    record_pending_cleanup,
)

log = get_logger(__name__)


def remove_local_graph_files(*, workspace_id: uuid.UUID, graph_id: uuid.UUID) -> None:
    """Delete ``{GRAPH_KB_DATA}/{workspace_id}/{graph_id}`` when it exists."""

    root = settings.resolve_graph_kb_data() / str(workspace_id) / str(graph_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def _send_cleanup_task(*, workspace_id: uuid.UUID, graph_id: uuid.UUID, engine: str) -> bool:
    """Dispatch ``graph_kb.cleanup`` onto the ``graph_kb`` queue when Celery is available."""

    from app.celery_app import celery_app

    if celery_app is None:
        log.warning("graph_kb.cleanup skipped: celery unavailable graph_id={}", graph_id)
        return False
    celery_app.send_task(
        GRAPH_KB_CLEANUP_TASK_NAME,
        args=[str(workspace_id), str(graph_id), engine],
        queue="graph_kb",
    )
    log.info("graph_kb.cleanup enqueued graph_id={} engine={}", graph_id, engine)
    return True


def flush_pending_cleanups() -> int:
    """Retry deferred cleanups recorded on disk; return how many were re-enqueued."""

    flushed = 0
    for entry in iter_pending_cleanups():
        try:
            workspace_id = uuid.UUID(str(entry["workspace_id"]))
            graph_id = uuid.UUID(str(entry["graph_id"]))
            engine = str(entry["engine"])
        except (KeyError, TypeError, ValueError):
            log.warning("graph_kb.cleanup pending_invalid entry={}", entry)
            continue
        if _send_cleanup_task(workspace_id=workspace_id, graph_id=graph_id, engine=engine):
            clear_pending_cleanup(workspace_id=workspace_id, graph_id=graph_id)
            flushed += 1
    return flushed


async def enqueue_cleanup(
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    engine: str,
    user_id: uuid.UUID | None = None,
) -> None:
    """Enqueue Worker + local-file cleanup after SQL rows are already gone.

    Failures are logged and do not raise — DELETE API must still succeed (spec §5.7).
    When Celery is unavailable, a pending file is written for later ``flush_pending_cleanups``.
    ``user_id`` is accepted for call-site compatibility and is unused (no orphan job row).
    """

    _ = user_id
    try:
        flush_pending_cleanups()
        if _send_cleanup_task(workspace_id=workspace_id, graph_id=graph_id, engine=engine):
            clear_pending_cleanup(workspace_id=workspace_id, graph_id=graph_id)
        else:
            record_pending_cleanup(
                workspace_id=workspace_id, graph_id=graph_id, engine=engine
            )
    except Exception:
        log.exception("graph_kb.cleanup enqueue_failed graph_id={}", graph_id)
        record_pending_cleanup(workspace_id=workspace_id, graph_id=graph_id, engine=engine)


async def run_cleanup_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    engine: str,
) -> dict[str, Any]:
    """Remove local graph files and call Worker ``delete_namespace``.

    ``session`` is unused: SQL rows were already deleted in the DELETE API transaction.
    """

    _ = session
    remove_local_graph_files(workspace_id=workspace_id, graph_id=graph_id)
    client = create_engine_client()
    await client.delete_namespace(engine=engine, workspace_id=workspace_id, graph_id=graph_id)
    clear_pending_cleanup(workspace_id=workspace_id, graph_id=graph_id)
    log.info("graph_kb.cleanup done graph_id={} engine={}", graph_id, engine)
    return {
        "workspace_id": str(workspace_id),
        "graph_id": str(graph_id),
        "engine": engine,
    }
