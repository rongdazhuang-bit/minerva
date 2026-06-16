"""Business logic for dataset list, detail, update, and delete."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.log import get_logger
from app.dataset.domain.constants import (
    DATASET_CLEANUP_TASK_NAME,
    INDEXING_STATUS_COMPLETED,
    INDEXING_TECHNIQUE_ECONOMY,
    INDEXING_TECHNIQUE_HIGH_QUALITY,
)
from app.dataset.domain.db.models import Dataset, DatasetDocument, DatasetProcessRule
from app.dataset.infrastructure import repository as repo
from app.dataset.service.chunk_service import deserialize_process_rule, serialize_process_rule
from app.dataset.service.deletion_service import (
    build_dataset_cleanup_manifest,
    delete_dataset_cascade,
)
from app.exceptions import AppError

log = get_logger(__name__)


async def require_dataset(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> Dataset:
    """Load dataset or raise 404."""

    row = await repo.get_dataset_for_workspace(
        session, workspace_id=workspace_id, dataset_id=dataset_id
    )
    if row is None:
        raise AppError("dataset.not_found", "知识库不存在。", 404)
    return row


async def list_dataset_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    name: str | None = None,
    indexing_technique: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> tuple[list[dict], int]:
    """List datasets with document counts for API responses."""

    rows, total = await repo.list_datasets_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        name=name,
        indexing_technique=indexing_technique,
        created_from=created_from,
        created_to=created_to,
    )
    items: list[dict] = []
    for row in rows:
        doc_count = await repo.count_documents_for_dataset(session, dataset_id=row.id)
        items.append(
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "indexing_technique": row.indexing_technique,
                "document_count": doc_count,
                "create_at": row.create_at,
                "update_at": row.update_at,
            }
        )
    return items, total


async def get_dataset_detail(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> dict[str, Any]:
    """Return dataset detail payload."""

    row = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    doc_count = await repo.count_documents_for_dataset(session, dataset_id=row.id)
    process_rule = await repo.get_latest_process_rule(session, dataset_id=row.id)
    process_rule_payload = (
        deserialize_process_rule(process_rule.rules) if process_rule is not None else None
    )
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "indexing_technique": row.indexing_technique,
        "embedding_model": row.embedding_model,
        "embedding_model_provider": row.embedding_model_provider,
        "retrieval_model": row.retrieval_model,
        "chunk_structure": row.chunk_structure,
        "document_count": doc_count,
        "process_rule_id": process_rule.id if process_rule else None,
        "process_rule": process_rule_payload,
        "create_at": row.create_at,
        "update_at": row.update_at,
    }


async def update_dataset(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    user_id: uuid.UUID,
    patch: dict[str, Any],
) -> Dataset:
    """Patch dataset metadata and settings."""

    row = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    if "name" in patch and patch["name"] is not None:
        row.name = str(patch["name"]).strip()
    if "description" in patch:
        row.description = patch["description"]
    if "retrieval_model" in patch and patch["retrieval_model"] is not None:
        row.retrieval_model = patch["retrieval_model"]
    if "indexing_technique" in patch and patch["indexing_technique"] is not None:
        new_technique = str(patch["indexing_technique"]).strip()
        if (
            row.indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY
            and new_technique == INDEXING_TECHNIQUE_ECONOMY
        ):
            completed = await repo.count_documents_by_status(
                session,
                dataset_id=row.id,
                indexing_status=INDEXING_STATUS_COMPLETED,
            )
            if completed > 0:
                raise AppError(
                    "dataset.indexing_downgrade_forbidden",
                    "已有高质量索引文档，不能改回经济模式。",
                    422,
                )
        row.indexing_technique = new_technique
    if "embedding_model" in patch:
        row.embedding_model = patch["embedding_model"]
    if "embedding_model_provider" in patch:
        row.embedding_model_provider = patch["embedding_model_provider"]
    if "process_rule" in patch and patch["process_rule"] is not None:
        rule_payload = patch["process_rule"]
        process_row = DatasetProcessRule(
            id=uuid.uuid4(),
            dataset_id=row.id,
            mode=str(rule_payload.get("mode") or "custom"),
            rules=serialize_process_rule(rule_payload),
            created_by=user_id,
        )
        session.add(process_row)
    row.updated_by = user_id
    row.update_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(row)
    return row


def _enqueue_dataset_cleanup(manifest: dict[str, Any]) -> str | None:
    """Send async cleanup task for uploads, S3, and vector collection."""

    if celery_app is None:
        log.warning(
            "dataset.cleanup skipped: celery unavailable dataset_id={}",
            manifest.get("dataset_id"),
        )
        return None
    try:
        result = celery_app.send_task(
            DATASET_CLEANUP_TASK_NAME,
            args=[manifest],
            queue="dataset",
        )
        return str(result.id)
    except Exception:
        log.exception(
            "dataset.cleanup enqueue_failed dataset_id={}",
            manifest.get("dataset_id"),
        )
        return None


async def delete_dataset(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> None:
    """Delete one knowledge base, enqueue async external cleanup."""

    row = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    documents = list(
        (
            await session.scalars(
                select(DatasetDocument).where(DatasetDocument.dataset_id == dataset_id)
            )
        ).all()
    )
    manifest = await build_dataset_cleanup_manifest(
        session,
        workspace_id=row.workspace_id,
        dataset_id=row.id,
        documents=documents,
        indexing_technique=row.indexing_technique,
    )
    await delete_dataset_cascade(session, dataset=row)
    await session.commit()
    _enqueue_dataset_cleanup(manifest)


async def create_empty_dataset(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create an empty knowledge base with default process rule (Dify POST /datasets)."""

    from app.dataset.domain.constants import (
        DATA_SOURCE_UPLOAD_FILE,
        DEFAULT_PROCESS_RULE,
        DEFAULT_RETRIEVAL_MODEL,
        DOC_FORM_TEXT,
    )

    label = name.strip()
    if not label:
        raise AppError("dataset.name_required", "知识库名称不能为空。", 422)

    dataset_id = uuid.uuid4()
    dataset = Dataset(
        id=dataset_id,
        workspace_id=workspace_id,
        name=label,
        description=description,
        data_source_type=DATA_SOURCE_UPLOAD_FILE,
        retrieval_model=DEFAULT_RETRIEVAL_MODEL,
        chunk_structure=DOC_FORM_TEXT,
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(dataset)
    session.add(
        DatasetProcessRule(
            id=uuid.uuid4(),
            dataset_id=dataset.id,
            mode=str(DEFAULT_PROCESS_RULE.get("mode") or "custom"),
            rules=serialize_process_rule(DEFAULT_PROCESS_RULE),
            created_by=user_id,
        )
    )
    await session.commit()
    return await get_dataset_detail(session, workspace_id=workspace_id, dataset_id=dataset.id)
