"""Cascade delete helpers for dataset tables and vector indexes."""

from __future__ import annotations

import json
import uuid
from typing import Any, TypedDict

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.constants import INDEXING_TECHNIQUE_HIGH_QUALITY
from app.dataset.domain.db.models import (
    Dataset,
    DatasetChildChunk,
    DatasetDocument,
    DatasetDocumentSegment,
    DatasetKeywordTable,
    DatasetProcessRule,
    DatasetQuery,
    DatasetUploadFile,
)
from app.dataset.infrastructure.vector.base import VectorFactory, vector_type_for_dataset


class DatasetCleanupUpload(TypedDict):
    """One upload file entry in a dataset cleanup manifest."""

    id: str
    storage_key: str


class DatasetCleanupManifest(TypedDict):
    """Payload for async dataset external resource cleanup."""

    workspace_id: str
    dataset_id: str
    indexing_technique: str | None
    uploads: list[DatasetCleanupUpload]


async def delete_vector_collection(dataset: Dataset) -> None:
    """Drop pgvector table for a high-quality dataset when present."""

    if dataset.indexing_technique != INDEXING_TECHNIQUE_HIGH_QUALITY:
        return
    collection = Dataset.gen_collection_name(dataset.id)
    vector = VectorFactory.build(collection, vector_type=vector_type_for_dataset(dataset))
    if hasattr(vector, "delete_collection"):
        vector.delete_collection()  # type: ignore[attr-defined]


async def delete_vector_nodes_for_document(dataset: Dataset, document_id: uuid.UUID) -> None:
    """Remove vector rows belonging to one document."""

    if dataset.indexing_technique != INDEXING_TECHNIQUE_HIGH_QUALITY:
        return
    collection = Dataset.gen_collection_name(dataset.id)
    vector = VectorFactory.build(collection, vector_type=vector_type_for_dataset(dataset))
    vector.delete_by_metadata_field("document_id", str(document_id))


async def delete_segments_for_document(session: AsyncSession, *, document_id: uuid.UUID) -> None:
    """Delete child chunks and segments for one document."""

    await session.execute(
        delete(DatasetChildChunk).where(DatasetChildChunk.document_id == document_id)
    )
    await session.execute(
        delete(DatasetDocumentSegment).where(DatasetDocumentSegment.document_id == document_id)
    )


async def delete_document_cascade(
    session: AsyncSession,
    *,
    dataset: Dataset,
    document: DatasetDocument,
) -> None:
    """Delete one document and its dependent rows plus vector nodes."""

    await delete_vector_nodes_for_document(dataset, document.id)
    await delete_segments_for_document(session, document_id=document.id)
    await session.delete(document)


async def delete_dataset_cascade(
    session: AsyncSession,
    *,
    dataset: Dataset,
) -> None:
    """Delete dataset and all dependent rows in spec order."""

    dataset_id = dataset.id
    doc_ids = list(
        (
            await session.scalars(
                select(DatasetDocument.id).where(DatasetDocument.dataset_id == dataset_id)
            )
        ).all()
    )
    for doc_id in doc_ids:
        await session.execute(
            delete(DatasetChildChunk).where(DatasetChildChunk.document_id == doc_id)
        )
    await session.execute(
        delete(DatasetDocumentSegment).where(DatasetDocumentSegment.dataset_id == dataset_id)
    )
    await session.execute(delete(DatasetDocument).where(DatasetDocument.dataset_id == dataset_id))
    await session.execute(delete(DatasetProcessRule).where(DatasetProcessRule.dataset_id == dataset_id))
    await session.execute(delete(DatasetKeywordTable).where(DatasetKeywordTable.dataset_id == dataset_id))
    await session.execute(delete(DatasetQuery).where(DatasetQuery.dataset_id == dataset_id))
    await session.delete(dataset)


def _parse_upload_id(document: DatasetDocument) -> uuid.UUID | None:
    """Resolve upload file id from document file_id or data_source_info."""

    if document.file_id:
        try:
            return uuid.UUID(str(document.file_id))
        except ValueError:
            pass
    raw = document.data_source_info
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        return None
    upload_ref = info.get("upload_file_id")
    if not upload_ref:
        return None
    try:
        return uuid.UUID(str(upload_ref))
    except ValueError:
        return None


async def upload_referenced_by_other_dataset(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    upload_id: uuid.UUID,
    exclude_dataset_id: uuid.UUID,
) -> bool:
    """Return True when another dataset in the workspace still references the upload."""

    count = await session.scalar(
        select(func.count())
        .select_from(DatasetDocument)
        .where(
            DatasetDocument.workspace_id == workspace_id,
            DatasetDocument.dataset_id != exclude_dataset_id,
            DatasetDocument.file_id == str(upload_id),
        )
    )
    return int(count or 0) > 0


async def build_dataset_cleanup_manifest(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    documents: list[DatasetDocument],
    indexing_technique: str | None,
) -> DatasetCleanupManifest:
    """Collect upload files eligible for async cleanup after dataset SQL delete."""

    uploads: list[DatasetCleanupUpload] = []
    seen: set[uuid.UUID] = set()
    for document in documents:
        upload_id = _parse_upload_id(document)
        if upload_id is None or upload_id in seen:
            continue
        seen.add(upload_id)
        if await upload_referenced_by_other_dataset(
            session,
            workspace_id=workspace_id,
            upload_id=upload_id,
            exclude_dataset_id=dataset_id,
        ):
            continue
        row = await session.get(DatasetUploadFile, upload_id)
        if row is None:
            continue
        uploads.append({"id": str(row.id), "storage_key": row.storage_key})
    return {
        "workspace_id": str(workspace_id),
        "dataset_id": str(dataset_id),
        "indexing_technique": indexing_technique,
        "uploads": uploads,
    }
