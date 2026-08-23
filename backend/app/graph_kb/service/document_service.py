"""GraphKB document import (upload / plain text), list, and delete."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    ALLOWED_UPLOAD_SUFFIXES,
    SOURCE_PLAIN_TEXT,
    SOURCE_UPLOAD_FILE,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
)
from app.graph_kb.domain.acl import GraphAclActor
from app.graph_kb.domain.db.models import GraphKbDocument
from app.graph_kb.service import graph_service as graph_svc
from app.graph_kb.service.index_service import enqueue_index

# Preview length kept in ``text_content`` when the body is spilled to disk.
_TEXT_PREVIEW_CHARS = 500


def validate_upload_filename(filename: str) -> str:
    """Return lowercase suffix (with dot) or raise ``graph_kb.file_type_unsupported``."""

    label = (filename or "").strip()
    if not label:
        raise AppError("graph_kb.file_required", "请上传文件。", 400)
    suffix = Path(label).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise AppError(
            "graph_kb.file_type_unsupported",
            "不支持的文件类型。",
            400,
        )
    return suffix


def validate_plain_text(text: str) -> str:
    """Strip and require non-empty plain text; raise ``graph_kb.text_required``."""

    body = (text or "").strip()
    if not body:
        raise AppError("graph_kb.text_required", "纯文本内容不能为空。", 400)
    return body


def _text_storage_rel(
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    document_id: uuid.UUID,
) -> str:
    """Relative path under ``resolve_graph_kb_data`` for spilled plain text."""

    return f"{workspace_id}/{graph_id}/texts/{document_id}.txt"


def _upload_storage_rel(
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    document_id: uuid.UUID,
    suffix: str,
) -> str:
    """Relative path under ``resolve_graph_kb_data`` for an uploaded file."""

    return f"{workspace_id}/{graph_id}/files/{document_id}{suffix}"


def _write_bytes(rel_key: str, payload: bytes) -> None:
    """Create parent dirs and write ``payload`` at ``resolve_graph_kb_data()/rel_key``."""

    root = settings.resolve_graph_kb_data()
    path = root / rel_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _unlink_storage_key(storage_key: str | None) -> None:
    """Best-effort delete of a local GraphKB object under the data root."""

    if not storage_key:
        return
    path = settings.resolve_graph_kb_data() / storage_key
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


async def add_plain_text(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    name: str,
    text: str,
) -> GraphKbDocument:
    """Create a plain-text document; spill oversize bodies to disk with a 500-char preview."""

    await graph_svc.get_graph_for_manage(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    body = validate_plain_text(text)
    label = (name or "").strip() or "untitled.txt"
    document_id = uuid.uuid4()
    storage_key: str | None = None
    text_content: str | None = body
    size_bytes = len(body.encode("utf-8"))

    if len(body) > settings.graph_kb_inline_text_max_chars:
        storage_key = _text_storage_rel(
            workspace_id=workspace_id, graph_id=graph_id, document_id=document_id
        )
        _write_bytes(storage_key, body.encode("utf-8"))
        text_content = body[:_TEXT_PREVIEW_CHARS]

    row = GraphKbDocument(
        id=document_id,
        workspace_id=workspace_id,
        graph_id=graph_id,
        source_type=SOURCE_PLAIN_TEXT,
        name=label[:255],
        storage_key=storage_key,
        text_content=text_content,
        mime_type="text/plain",
        size_bytes=size_bytes,
        indexing_status=STATUS_PENDING,
        created_by=actor.user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def add_upload_file(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    file: UploadFile,
) -> GraphKbDocument:
    """Persist an uploaded file under the GraphKB data root and register a document row."""

    await graph_svc.get_graph_for_manage(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    filename = file.filename or ""
    suffix = validate_upload_filename(filename)
    payload = await file.read()
    document_id = uuid.uuid4()
    storage_key = _upload_storage_rel(
        workspace_id=workspace_id,
        graph_id=graph_id,
        document_id=document_id,
        suffix=suffix,
    )
    _write_bytes(storage_key, payload)

    row = GraphKbDocument(
        id=document_id,
        workspace_id=workspace_id,
        graph_id=graph_id,
        source_type=SOURCE_UPLOAD_FILE,
        name=filename.strip()[:255],
        storage_key=storage_key,
        text_content=None,
        mime_type=file.content_type,
        size_bytes=len(payload),
        indexing_status=STATUS_PENDING,
        created_by=actor.user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def list_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    page: int,
    page_size: int,
) -> tuple[list[GraphKbDocument], int]:
    """Return a page of documents for a graph the actor may view."""

    await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    filters = (
        GraphKbDocument.workspace_id == workspace_id,
        GraphKbDocument.graph_id == graph_id,
    )
    total = int(
        await session.scalar(select(func.count()).select_from(GraphKbDocument).where(*filters))
        or 0
    )
    offset = max(page - 1, 0) * page_size
    stmt = (
        select(GraphKbDocument)
        .where(*filters)
        .order_by(GraphKbDocument.create_at.desc().nullslast(), GraphKbDocument.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list((await session.scalars(stmt)).all())
    return rows, total


async def delete_document(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    document_id: uuid.UUID,
    actor: GraphAclActor,
) -> dict[str, Any]:
    """Delete a document row; unlink storage only after a successful DB commit.

    Order: delete row → optional ``enqueue_index`` → commit → unlink file.
    Model binding errors (400) re-raise before commit so the row and file both
    remain. Job conflicts still return 200 with ``reindex_enqueued=false``.
    """

    graph = await graph_svc.get_graph_for_manage(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    stmt = select(GraphKbDocument).where(
        GraphKbDocument.id == document_id,
        GraphKbDocument.workspace_id == workspace_id,
        GraphKbDocument.graph_id == graph_id,
    )
    row = await session.scalar(stmt)
    if row is None:
        raise AppError("graph_kb.document_not_found", "文档不存在。", 404)

    storage_key = row.storage_key
    await session.execute(
        delete(GraphKbDocument).where(
            GraphKbDocument.id == document_id,
            GraphKbDocument.workspace_id == workspace_id,
            GraphKbDocument.graph_id == graph_id,
        )
    )
    await session.flush()

    reindex_enqueued = False
    message: str | None = None
    if graph.indexing_status in {STATUS_COMPLETED, STATUS_FAILED}:
        try:
            job = await enqueue_index(
                session,
                workspace_id=workspace_id,
                graph_id=graph_id,
                user_id=actor.user_id,
            )
            if job is not None:
                reindex_enqueued = True
            else:
                message = "文档已删除；自动重建索引未入队，请手动 POST /index。"
        except AppError as exc:
            if exc.code == "graph_kb.job_conflict" or exc.status_code == 409:
                message = "文档已删除；已有进行中的索引任务，请稍后手动 POST /index。"
            else:
                # Model 400 (etc.): do not commit or unlink — row + file stay.
                raise

    # enqueue_index may already have committed; otherwise persist the delete now.
    await session.commit()
    _unlink_storage_key(storage_key)

    return {
        "document_id": document_id,
        "reindex_enqueued": reindex_enqueued,
        "message": message,
    }
