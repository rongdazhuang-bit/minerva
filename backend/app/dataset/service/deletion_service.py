"""Cascade delete helpers for dataset tables and vector indexes."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
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
)
from app.dataset.infrastructure.vector.base import VectorFactory, vector_type_for_dataset


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
    await delete_vector_collection(dataset)
    await session.delete(dataset)
