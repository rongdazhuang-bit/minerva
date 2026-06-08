"""Business logic for dataset document segments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.constants import DOC_FORM_HIERARCHICAL, INDEXING_STATUS_COMPLETED
from app.dataset.domain.db.models import DatasetChildChunk, DatasetDocumentSegment
from app.dataset.infrastructure import repository as repo
from app.dataset.service.dataset_service import require_dataset
from app.dataset.service.index_sync_service import (
    remove_child_chunk_index,
    remove_segment_indexes,
    sync_child_chunk_index,
    sync_segment_indexes,
)
from app.exceptions import AppError


def _segment_dict(row: DatasetDocumentSegment, *, child_count: int = 0) -> dict[str, Any]:
    """Serialize one segment row."""

    payload = {
        "id": row.id,
        "position": row.position,
        "content": row.content,
        "word_count": row.word_count,
        "tokens": row.tokens,
        "enabled": row.enabled,
        "status": row.status,
        "hit_count": row.hit_count,
        "create_at": row.create_at,
        "update_at": row.update_at,
    }
    if row.answer:
        payload["answer"] = row.answer
    if child_count > 0:
        payload["child_count"] = child_count
    return payload


def _child_chunk_dict(row) -> dict[str, Any]:
    """Serialize one child chunk row."""

    return {
        "id": row.id,
        "position": row.position,
        "content": row.content,
        "word_count": row.word_count,
        "index_node_id": row.index_node_id,
        "create_at": row.create_at,
        "update_at": row.update_at,
    }


async def list_segment_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List segments for one document."""

    await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    rows, total = await repo.list_segments_page(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
    )
    segment_ids = [row.id for row in rows]
    child_counts = await repo.count_child_chunks_for_segments(
        session,
        dataset_id=dataset_id,
        segment_ids=segment_ids,
    )
    return [
        _segment_dict(row, child_count=child_counts.get(row.id, 0)) for row in rows
    ], total


async def list_child_chunks(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """List child chunks for one parent segment."""

    await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    segment = await repo.get_segment_for_document(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    if segment is None:
        raise AppError("dataset.segment_not_found", "分段不存在。", 404)
    rows = await repo.list_child_chunks_for_segment(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    return [_child_chunk_dict(row) for row in rows]


async def _require_hierarchical_segment(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
):
    """Load dataset, document, and segment for hierarchical child-chunk APIs."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    doc_form = (document.doc_form or dataset.chunk_structure or "text_model").strip()
    if doc_form != DOC_FORM_HIERARCHICAL:
        raise AppError(
            "dataset.child_chunk_not_supported",
            "仅父子分段模式支持子块操作。",
            422,
        )
    segment = await repo.get_segment_for_document(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    if segment is None:
        raise AppError("dataset.segment_not_found", "分段不存在。", 404)
    return dataset, document, segment


async def create_child_chunk(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
) -> dict[str, Any]:
    """Create one child chunk and index it (Dify POST child_chunks)."""

    text = content.strip()
    if not text:
        raise AppError("dataset.child_chunk_content_required", "子块内容不能为空。", 422)
    dataset, document, segment = await _require_hierarchical_segment(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    position = (
        await repo.max_child_chunk_position(
            session,
            dataset_id=dataset_id,
            document_id=document_id,
            segment_id=segment_id,
        )
        + 1
    )
    child = DatasetChildChunk(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        position=position,
        content=text,
        word_count=len(text),
        index_node_id=str(uuid.uuid4()),
        type="customized",
        created_by=user_id,
    )
    session.add(child)
    await session.flush()
    await sync_child_chunk_index(
        session,
        dataset=dataset,
        document=document,
        segment=segment,
        child=child,
    )
    await session.commit()
    await session.refresh(child)
    return _child_chunk_dict(child)


async def update_child_chunk(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    child_chunk_id: uuid.UUID,
    content: str,
) -> dict[str, Any]:
    """Update child chunk content and rebuild its index (Dify PATCH child_chunks)."""

    text = content.strip()
    if not text:
        raise AppError("dataset.child_chunk_content_required", "子块内容不能为空。", 422)
    dataset, document, segment = await _require_hierarchical_segment(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    child = await repo.get_child_chunk_for_segment(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        child_chunk_id=child_chunk_id,
    )
    if child is None:
        raise AppError("dataset.child_chunk_not_found", "子块不存在。", 404)
    await remove_child_chunk_index(session, dataset=dataset, child=child)
    child.content = text
    child.word_count = len(text)
    child.update_at = datetime.now(tz=UTC)
    await sync_child_chunk_index(
        session,
        dataset=dataset,
        document=document,
        segment=segment,
        child=child,
    )
    await session.commit()
    await session.refresh(child)
    return _child_chunk_dict(child)


async def delete_child_chunk(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    child_chunk_id: uuid.UUID,
) -> None:
    """Delete one child chunk and remove its index (Dify DELETE child_chunks)."""

    dataset, _document, _segment = await _require_hierarchical_segment(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    child = await repo.get_child_chunk_for_segment(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        child_chunk_id=child_chunk_id,
    )
    if child is None:
        raise AppError("dataset.child_chunk_not_found", "子块不存在。", 404)
    await remove_child_chunk_index(session, dataset=dataset, child=child)
    await session.delete(child)
    await session.commit()


async def create_segment(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
) -> dict[str, Any]:
    """Create one segment and sync indexes."""

    text = content.strip()
    if not text:
        raise AppError("dataset.segment_content_required", "分段内容不能为空。", 422)
    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    position = await repo.max_segment_position(
        session, dataset_id=dataset_id, document_id=document_id
    ) + 1
    row = DatasetDocumentSegment(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        position=position,
        content=text,
        word_count=len(text),
        tokens=max(1, len(text) // 4),
        enabled=True,
        status=INDEXING_STATUS_COMPLETED,
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    child_count = await sync_segment_indexes(
        session,
        dataset=dataset,
        document=document,
        segment=row,
        user_id=user_id,
    )
    await session.commit()
    await session.refresh(row)
    return _segment_dict(row, child_count=child_count)


async def update_segment(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    content: str,
) -> dict[str, Any]:
    """Update segment content and rebuild indexes."""

    text = content.strip()
    if not text:
        raise AppError("dataset.segment_content_required", "分段内容不能为空。", 422)
    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    row = await repo.get_segment_for_document(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    if row is None:
        raise AppError("dataset.segment_not_found", "分段不存在。", 404)
    row.content = text
    row.word_count = len(text)
    row.tokens = max(1, len(text) // 4)
    row.update_at = datetime.now(tz=UTC)
    child_count = await sync_segment_indexes(
        session,
        dataset=dataset,
        document=document,
        segment=row,
        user_id=document.created_by,
    )
    await session.commit()
    await session.refresh(row)
    return _segment_dict(row, child_count=child_count)


async def delete_segment(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> None:
    """Delete one segment and remove index entries."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    row = await repo.get_segment_for_document(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    if row is None:
        raise AppError("dataset.segment_not_found", "分段不存在。", 404)
    await remove_segment_indexes(
        session,
        dataset=dataset,
        document=document,
        segment=row,
    )
    await session.delete(row)
    await session.commit()


async def set_segment_enabled(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    enabled: bool,
) -> dict[str, Any]:
    """Enable or disable one segment."""

    await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    row = await repo.get_segment_for_document(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    if row is None:
        raise AppError("dataset.segment_not_found", "分段不存在。", 404)
    row.enabled = enabled
    row.update_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(row)
    return _segment_dict(row)
