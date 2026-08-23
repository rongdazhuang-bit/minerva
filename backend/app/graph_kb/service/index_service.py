"""Enqueue and run GraphKB index / reindex jobs; redact secrets in job.error."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.log import get_logger
from app.dataset.rag.extract import extract_text_from_bytes
from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    GRAPH_KB_INDEX_TASK_NAME,
    JOB_INDEX,
    JOB_REINDEX,
    SOURCE_PLAIN_TEXT,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from app.graph_kb.domain.db.models import GraphKb, GraphKbDocument, GraphKbJob
from app.graph_kb.engine.factory import create_engine_client
from app.graph_kb.engine.types import ModelEndpoint, WorkerDocument, WorkerIndexRequest
from app.graph_kb.service.model_resolver import resolve_graph_models
from app.graph_kb.service.projection_service import replace_projections
from app.llm.domain.resolved_model import ResolvedModel

log = get_logger(__name__)

# Index/reindex statuses that block a new enqueue (spec §5.4).
_ACTIVE_INDEX_STATUSES = frozenset({STATUS_PENDING, STATUS_RUNNING})
# Job kinds that compete for the single in-flight index slot.
_INDEX_KINDS = frozenset({JOB_INDEX, JOB_REINDEX})


def _job_field(job: Any, name: str) -> Any:
    """Read ``kind`` / ``status`` from a dict or ORM-like object."""

    if isinstance(job, dict):
        return job.get(name)
    return getattr(job, name, None)


def assert_no_active_index_job(jobs: list[Any]) -> None:
    """Raise ``graph_kb.job_conflict`` (409) if an index/reindex job is pending or running."""

    for job in jobs:
        kind = _job_field(job, "kind")
        status = _job_field(job, "status")
        if kind in _INDEX_KINDS and status in _ACTIVE_INDEX_STATUSES:
            raise AppError(
                "graph_kb.job_conflict",
                "已有进行中的图谱索引任务。",
                409,
            )


def redact_secret(key: str | None) -> str:
    """Mask a secret as ``***`` plus last 4 chars, or ``***`` when too short."""

    if not key or len(key) <= 4:
        return "***"
    return f"***{key[-4:]}"


def redact_job_error(message: str, secrets: list[str | None]) -> str:
    """Replace any occurrence of known secrets in ``message`` with ``redact_secret``."""

    out = message
    for secret in secrets:
        if secret and secret in out:
            out = out.replace(secret, redact_secret(secret))
    return out


def _endpoint_from_resolved(model: ResolvedModel) -> ModelEndpoint:
    """Build a worker ``ModelEndpoint`` from a resolved Chat/Embedding model."""

    return ModelEndpoint(
        base_url=model.endpoint_url,
        api_key=model.api_key,
        model=model.model_name,
    )


def load_document_text(document: GraphKbDocument) -> str:
    """Load full document text from spilled storage or inline ``text_content``."""

    if document.storage_key:
        path = settings.resolve_graph_kb_data() / document.storage_key
        if document.source_type == SOURCE_PLAIN_TEXT:
            return path.read_text(encoding="utf-8") if path.is_file() else (document.text_content or "")
        payload = path.read_bytes() if path.is_file() else b""
        return extract_text_from_bytes(payload, file_name=document.name)
    return document.text_content or ""


def _send_index_task(job_id: uuid.UUID) -> None:
    """Dispatch ``graph_kb.index`` onto the ``graph_kb`` queue when Celery is available."""

    from app.celery_app import celery_app

    if celery_app is None:
        log.warning("graph_kb.index skipped: celery unavailable job_id={}", job_id)
        return
    celery_app.send_task(
        GRAPH_KB_INDEX_TASK_NAME,
        args=[str(job_id)],
        queue="graph_kb",
    )
    log.info("graph_kb.index enqueued job_id={}", job_id)


async def enqueue_index(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    user_id: uuid.UUID,
) -> GraphKbJob:
    """Create a pending index/reindex job and enqueue Celery ``graph_kb.index``.

    Raises ``graph_kb.job_conflict`` (409) when another index/reindex is pending or running.
    Raises 400 from ``resolve_graph_models`` when Chat/Embedding bindings are unusable.
    """

    graph = await session.scalar(
        select(GraphKb).where(GraphKb.id == graph_id, GraphKb.workspace_id == workspace_id)
    )
    if graph is None:
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)

    await resolve_graph_models(
        session,
        workspace_id=workspace_id,
        llm_provider=graph.llm_model_provider,
        llm_name=graph.llm_model,
        emb_provider=graph.embedding_model_provider,
        emb_name=graph.embedding_model,
    )

    existing = list(
        (
            await session.scalars(
                select(GraphKbJob).where(
                    GraphKbJob.workspace_id == workspace_id,
                    GraphKbJob.graph_id == graph_id,
                )
            )
        ).all()
    )
    assert_no_active_index_job(existing)

    kind = JOB_REINDEX if graph.indexing_status in {STATUS_COMPLETED, STATUS_FAILED} else JOB_INDEX
    job = GraphKbJob(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        graph_id=graph_id,
        kind=kind,
        status=STATUS_PENDING,
        created_by=user_id,
    )
    session.add(job)
    graph.indexing_status = STATUS_PENDING
    await session.flush()
    await session.commit()
    await session.refresh(job)
    _send_index_task(job.id)
    return job


async def run_index_job(session: AsyncSession, *, job_id: uuid.UUID) -> dict[str, Any]:
    """Run one index job: Worker ``index``, then write projections only on success.

    On any exception after projection work begins, roll back so a half-applied
    ``replace_projections`` cannot wipe the last good snapshot; then re-fetch
    and persist failed status only. ``api_key`` values from
    ``resolve_graph_models`` are redacted in ``job.error``.
    """

    job = await session.get(GraphKbJob, job_id)
    if job is None:
        raise AppError("graph_kb.job_not_found", "索引任务不存在。", 404)

    graph = await session.scalar(
        select(GraphKb).where(GraphKb.id == job.graph_id, GraphKb.workspace_id == job.workspace_id)
    )
    if graph is None:
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)

    now = datetime.now(tz=UTC)
    job.status = STATUS_RUNNING
    job.started_at = now
    job.error = None
    graph.indexing_status = STATUS_RUNNING
    await session.flush()

    documents = list(
        (
            await session.scalars(
                select(GraphKbDocument).where(
                    GraphKbDocument.workspace_id == job.workspace_id,
                    GraphKbDocument.graph_id == job.graph_id,
                )
            )
        ).all()
    )
    secrets: list[str | None] = []

    try:
        llm, emb = await resolve_graph_models(
            session,
            workspace_id=job.workspace_id,
            llm_provider=graph.llm_model_provider,
            llm_name=graph.llm_model,
            emb_provider=graph.embedding_model_provider,
            emb_name=graph.embedding_model,
        )
        secrets.extend([llm.api_key, emb.api_key])
        worker_docs = [
            WorkerDocument(
                document_id=doc.id,
                name=doc.name,
                text=load_document_text(doc),
            )
            for doc in documents
        ]
        client = create_engine_client()
        await client.index(
            WorkerIndexRequest(
                workspace_id=job.workspace_id,
                graph_id=job.graph_id,
                engine=graph.engine,
                documents=worker_docs,
                llm=_endpoint_from_resolved(llm),
                embedding=_endpoint_from_resolved(emb),
            )
        )
        export = await client.export_graph(
            engine=graph.engine,
            workspace_id=job.workspace_id,
            graph_id=job.graph_id,
        )
        summaries = await client.list_summaries(
            engine=graph.engine,
            workspace_id=job.workspace_id,
            graph_id=job.graph_id,
        )
        await replace_projections(
            session,
            graph_id=job.graph_id,
            workspace_id=job.workspace_id,
            export=export,
            summaries=summaries,
        )
        finished = datetime.now(tz=UTC)
        job.status = STATUS_COMPLETED
        job.finished_at = finished
        job.error = None
        graph.indexing_status = STATUS_COMPLETED
        for doc in documents:
            doc.indexing_status = STATUS_COMPLETED
            doc.error = None
        await session.flush()
        await session.commit()
        log.info("graph_kb.index completed job_id={}", job_id)
        return {"job_id": str(job.id), "status": STATUS_COMPLETED}
    except Exception as exc:
        # Mirror dataset indexing_runner: rollback undoes deleted/inserted
        # projection rows so the previous successful snapshot remains.
        await session.rollback()
        error_msg = redact_job_error(str(exc), secrets)
        finished = datetime.now(tz=UTC)
        job = await session.get(GraphKbJob, job_id)
        if job is None:
            log.exception("graph_kb.index failed job_id={} (job missing after rollback)", job_id)
            return {"job_id": str(job_id), "status": STATUS_FAILED, "error": error_msg}
        graph = await session.scalar(
            select(GraphKb).where(GraphKb.id == job.graph_id, GraphKb.workspace_id == job.workspace_id)
        )
        documents = list(
            (
                await session.scalars(
                    select(GraphKbDocument).where(
                        GraphKbDocument.workspace_id == job.workspace_id,
                        GraphKbDocument.graph_id == job.graph_id,
                    )
                )
            ).all()
        )
        job.status = STATUS_FAILED
        job.finished_at = finished
        job.error = error_msg
        if graph is not None:
            graph.indexing_status = STATUS_FAILED
        for doc in documents:
            doc.indexing_status = STATUS_FAILED
            doc.error = error_msg
        await session.flush()
        await session.commit()
        log.exception("graph_kb.index failed job_id={}", job_id)
        return {"job_id": str(job.id), "status": STATUS_FAILED, "error": job.error}


async def get_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    job_id: uuid.UUID,
) -> GraphKbJob:
    """Load one job scoped to workspace + graph, or raise ``graph_kb.job_not_found``."""

    job = await session.scalar(
        select(GraphKbJob).where(
            GraphKbJob.id == job_id,
            GraphKbJob.workspace_id == workspace_id,
            GraphKbJob.graph_id == graph_id,
        )
    )
    if job is None:
        raise AppError("graph_kb.job_not_found", "索引任务不存在。", 404)
    return job
