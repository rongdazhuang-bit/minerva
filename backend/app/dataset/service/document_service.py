"""Business logic for dataset documents."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dataset.domain.constants import (
    DATA_SOURCE_UPLOAD_FILE,
    INDEXING_STATUS_ERROR,
    INDEXING_STATUS_WAITING,
)
from app.dataset.domain.db.models import Dataset, DatasetDocument, DatasetProcessRule, DatasetUploadFile
from app.dataset.domain.display_status import compute_display_status
from app.dataset.infrastructure import repository as repo
from app.dataset.service.dataset_service import require_dataset
from app.dataset.service.deletion_service import delete_document_cascade, delete_segments_for_document
from app.dataset.service.deletion_service import delete_vector_nodes_for_document
from app.dataset.service.init_service import _enqueue_indexing
from app.dataset.service.chunk_service import (
    load_document_process_rule_for_detail,
    serialize_process_rule,
)
from app.exceptions import AppError


def _document_to_dict(document: DatasetDocument, *, hit_count: int = 0) -> dict[str, Any]:
    """Serialize one document row for API responses."""

    return {
        "id": document.id,
        "name": document.name,
        "position": document.position,
        "indexing_status": document.indexing_status,
        "display_status": compute_display_status(document),
        "enabled": document.enabled,
        "archived": document.archived,
        "is_paused": bool(document.is_paused),
        "doc_form": document.doc_form or "text_model",
        "word_count": document.word_count,
        "hit_count": hit_count,
        "error": document.error,
        "batch": document.batch,
        "create_at": document.create_at,
        "update_at": document.update_at,
        "completed_at": document.completed_at,
    }


async def list_document_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List documents within one dataset."""

    await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    rows, total = await repo.list_documents_page(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
    )
    hit_counts = await repo.sum_segment_hit_counts_by_document_ids(
        session,
        document_ids=[row.id for row in rows],
    )
    return [
        _document_to_dict(row, hit_count=hit_counts.get(row.id, 0)) for row in rows
    ], total


async def get_document_detail(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """Return one document detail payload."""

    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    hit_counts = await repo.sum_segment_hit_counts_by_document_ids(
        session,
        document_ids=[document.id],
    )
    process_rule = await load_document_process_rule_for_detail(session, document=document)
    return {
        **_document_to_dict(document, hit_count=hit_counts.get(document.id, 0)),
        "file_id": document.file_id,
        "process_rule_id": document.dataset_process_rule_id,
        "process_rule": process_rule,
    }


async def get_document_indexing_status(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """Return indexing progress for one document (aligned with Dify status fields)."""

    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    total_segments, completed_segments = await repo.count_segments_for_document(
        session,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    return {
        "id": document.id,
        "name": document.name,
        "indexing_status": document.indexing_status,
        "display_status": compute_display_status(document),
        "error": document.error,
        "is_paused": bool(document.is_paused),
        "processing_started_at": document.processing_started_at,
        "parsing_completed_at": document.parsing_completed_at,
        "cleaning_completed_at": document.cleaning_completed_at,
        "splitting_completed_at": document.splitting_completed_at,
        "completed_at": document.completed_at,
        "stopped_at": document.stopped_at,
        "total_segments": total_segments,
        "completed_segments": completed_segments,
    }


async def append_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    dataset_id: uuid.UUID,
    file_ids: list[uuid.UUID],
    process_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append uploaded files to an existing dataset and enqueue indexing."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    if not file_ids:
        raise AppError("dataset.file_ids_required", "请至少选择一个文件。", 422)
    existing_count = await repo.count_documents_for_dataset(session, dataset_id=dataset.id)
    if existing_count + len(file_ids) > settings.dataset_max_files_per_dataset:
        raise AppError("dataset.too_many_files", "文件数量超过知识库上限。", 422)

    shared_rule: DatasetProcessRule | None = None
    if process_rule is None:
        shared_rule = await repo.get_latest_process_rule(session, dataset_id=dataset.id)
        if shared_rule is None:
            raise AppError("dataset.process_rule_missing", "知识库缺少分段规则。", 422)

    max_position = await repo.max_document_position(session, dataset_id=dataset.id)
    batch = uuid.uuid4().hex
    documents: list[DatasetDocument] = []
    for offset, upload_id in enumerate(file_ids, start=1):
        upload = await session.get(DatasetUploadFile, upload_id)
        if upload is None or upload.workspace_id != workspace_id:
            raise AppError("dataset.upload_not_found", "上传文件不存在。", 404)

        if process_rule is not None:
            rule_row = DatasetProcessRule(
                id=uuid.uuid4(),
                dataset_id=dataset.id,
                mode=str(process_rule.get("mode") or "custom"),
                rules=serialize_process_rule(process_rule),
                created_by=user_id,
            )
            session.add(rule_row)
            await session.flush()
            rule_id = rule_row.id
        else:
            rule_id = shared_rule.id  # type: ignore[union-attr]

        doc = DatasetDocument(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            dataset_id=dataset.id,
            position=max_position + offset,
            data_source_type=DATA_SOURCE_UPLOAD_FILE,
            data_source_info=json.dumps({"upload_file_id": str(upload_id)}),
            dataset_process_rule_id=rule_id,
            batch=batch,
            name=upload.name,
            created_from="web",
            created_by=user_id,
            file_id=str(upload_id),
            indexing_status=INDEXING_STATUS_WAITING,
            doc_form=dataset.chunk_structure or "text_model",
        )
        session.add(doc)
        documents.append(doc)
    await session.commit()
    for doc in documents:
        await session.refresh(doc)
    task_id = _enqueue_indexing(dataset.id, [doc.id for doc in documents])
    return {
        "batch": batch,
        "documents": [_document_to_dict(doc) for doc in documents],
        "indexing_task_id": task_id,
    }


async def delete_document(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """Delete one document and dependent rows."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    await delete_document_cascade(session, dataset=dataset, document=document)
    await session.commit()


async def set_document_enabled(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    enabled: bool,
) -> dict[str, Any]:
    """Enable or disable one document."""

    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    document.enabled = enabled
    document.update_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(document)
    return _document_to_dict(document)


async def retry_document(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """Reset failed document and re-enqueue indexing."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    if document.indexing_status != INDEXING_STATUS_ERROR:
        raise AppError("dataset.document_not_retryable", "仅失败文档可重试。", 422)
    await _reset_document_for_retry(session, dataset=dataset, document=document)
    await session.commit()
    _enqueue_indexing(dataset.id, [document.id])
    await session.refresh(document)
    return _document_to_dict(document)


async def set_document_paused(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    paused: bool,
) -> dict[str, Any]:
    """Pause or resume document processing flag."""

    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    document.is_paused = paused
    document.update_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(document)
    return _document_to_dict(document)


async def update_document(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Update mutable document fields such as name or per-document process_rule."""

    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    if "process_rule" in patch and patch["process_rule"] is not None and document.archived:
        raise AppError("dataset.document_archived", "已归档文档不可修改。", 422)
    if "name" in patch and patch["name"] is not None:
        name = str(patch["name"]).strip()
        if not name:
            raise AppError("dataset.document_name_required", "文档名称不能为空。", 422)
        document.name = name
    should_enqueue = False
    if "process_rule" in patch and patch["process_rule"] is not None:
        rule_payload = patch["process_rule"]
        process_row = DatasetProcessRule(
            id=uuid.uuid4(),
            dataset_id=document.dataset_id,
            mode=str(rule_payload.get("mode") or "custom"),
            rules=serialize_process_rule(rule_payload),
            created_by=user_id,
        )
        session.add(process_row)
        await session.flush()
        document.dataset_process_rule_id = process_row.id
        dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
        await reprocess_document(session, dataset=dataset, document=document)
        should_enqueue = True
    document.update_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(document)
    if should_enqueue:
        _enqueue_indexing(dataset_id, [document.id])
    return _document_to_dict(document)


async def reprocess_document(
    session: AsyncSession,
    *,
    dataset: Dataset,
    document: DatasetDocument,
) -> None:
    """Clear segments/vectors and reset document state before re-indexing."""

    await delete_vector_nodes_for_document(dataset, document.id)
    await delete_segments_for_document(session, document_id=document.id)
    document.indexing_status = INDEXING_STATUS_WAITING
    document.error = None
    document.is_paused = False
    document.processing_started_at = None
    document.parsing_completed_at = None
    document.cleaning_completed_at = None
    document.splitting_completed_at = None
    document.completed_at = None
    document.update_at = datetime.now(tz=UTC)


async def _reset_document_for_retry(
    session: AsyncSession,
    *,
    dataset: Dataset,
    document: DatasetDocument,
) -> None:
    """Clear failed document state and re-enqueue indexing."""

    await reprocess_document(session, dataset=dataset, document=document)


async def retry_failed_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> dict[str, Any]:
    """Retry all failed documents in one knowledge base."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    failed_rows = await repo.list_documents_by_indexing_status(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        indexing_status=INDEXING_STATUS_ERROR,
    )
    if not failed_rows:
        return {"retried_count": 0, "document_ids": []}
    document_ids: list[uuid.UUID] = []
    for document in failed_rows:
        await _reset_document_for_retry(session, dataset=dataset, document=document)
        document_ids.append(document.id)
    await session.commit()
    _enqueue_indexing(dataset.id, document_ids)
    return {"retried_count": len(document_ids), "document_ids": document_ids}
