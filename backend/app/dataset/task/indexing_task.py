"""Celery task entry for dataset document indexing."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from celery import Task, shared_task

from app.core.infrastructure.db.session import async_session_factory, engine
from app.core.log import get_logger
from app.dataset.domain.constants import DATASET_INDEXING_TASK_NAME
from app.dataset.rag.indexing_runner import run_documents_indexing

log = get_logger(__name__)


def _run_async(dataset_id: str, document_ids: list[str]) -> dict[str, Any]:
    """Run indexing on a dedicated event loop."""

    async def _runner() -> dict[str, Any]:
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_documents_indexing(
                    session,
                    dataset_id=uuid.UUID(dataset_id),
                    document_ids=[uuid.UUID(doc_id) for doc_id in document_ids],
                )
        finally:
            await engine.dispose(close=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_runner())


@shared_task(bind=True, name=DATASET_INDEXING_TASK_NAME)
def dataset_document_indexing_task(self: Task, dataset_id: str, document_ids: list[str]) -> dict[str, Any]:
    """Index one batch of dataset documents asynchronously."""

    log.info(
        "dataset.indexing start dataset_id={} document_count={} task_id={}",
        dataset_id,
        len(document_ids),
        getattr(self.request, "id", None),
    )
    summary = _run_async(dataset_id, document_ids)
    log.info("dataset.indexing done summary={}", summary)
    return summary
