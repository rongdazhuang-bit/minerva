"""Read/write queries for dataset tables."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.db.models import (
    Dataset,
    DatasetDocument,
    DatasetDocumentSegment,
    DatasetProcessRule,
)


async def list_datasets_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    name: str | None = None,
    indexing_technique: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> tuple[list[Dataset], int]:
    """Return paginated datasets for a workspace with optional filters."""

    filters = [Dataset.workspace_id == workspace_id]
    if name and name.strip():
        filters.append(Dataset.name.ilike(f"%{name.strip()}%"))
    if indexing_technique and indexing_technique.strip():
        filters.append(Dataset.indexing_technique == indexing_technique.strip())
    if created_from is not None:
        filters.append(Dataset.create_at >= created_from)
    if created_to is not None:
        filters.append(Dataset.create_at <= created_to)

    count_stmt = select(func.count()).select_from(Dataset).where(*filters)
    total = int((await session.scalar(count_stmt)) or 0)

    offset = (page - 1) * page_size
    rows_stmt = (
        select(Dataset)
        .where(*filters)
        .order_by(Dataset.create_at.desc().nullslast(), Dataset.name.asc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list((await session.scalars(rows_stmt)).all())
    return rows, total


async def get_dataset_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> Dataset | None:
    """Load one dataset scoped to workspace."""

    stmt = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    return await session.scalar(stmt)


async def count_documents_for_dataset(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
) -> int:
    """Count documents belonging to a dataset."""

    stmt = select(func.count()).select_from(DatasetDocument).where(
        DatasetDocument.dataset_id == dataset_id
    )
    return int((await session.scalar(stmt)) or 0)


async def list_documents_by_batch(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    batch: str,
) -> list[DatasetDocument]:
    """Load documents for one indexing batch."""

    stmt = (
        select(DatasetDocument)
        .where(
            DatasetDocument.workspace_id == workspace_id,
            DatasetDocument.dataset_id == dataset_id,
            DatasetDocument.batch == batch,
        )
        .order_by(DatasetDocument.position.asc())
    )
    return list((await session.scalars(stmt)).all())


async def count_documents_by_status(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    indexing_status: str,
) -> int:
    """Count documents with a given indexing status."""

    stmt = select(func.count()).select_from(DatasetDocument).where(
        DatasetDocument.dataset_id == dataset_id,
        DatasetDocument.indexing_status == indexing_status,
    )
    return int((await session.scalar(stmt)) or 0)


async def get_latest_process_rule(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
) -> DatasetProcessRule | None:
    """Return the newest process rule row for a dataset."""

    stmt = (
        select(DatasetProcessRule)
        .where(DatasetProcessRule.dataset_id == dataset_id)
        .order_by(DatasetProcessRule.create_at.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def max_document_position(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
) -> int:
    """Return highest document position in a dataset."""

    stmt = select(func.max(DatasetDocument.position)).where(DatasetDocument.dataset_id == dataset_id)
    return int((await session.scalar(stmt)) or 0)


async def list_documents_by_indexing_status(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    indexing_status: str,
) -> list[DatasetDocument]:
    """Return all documents with a given indexing status."""

    stmt = (
        select(DatasetDocument)
        .where(
            DatasetDocument.workspace_id == workspace_id,
            DatasetDocument.dataset_id == dataset_id,
            DatasetDocument.indexing_status == indexing_status,
        )
        .order_by(DatasetDocument.position.asc())
    )
    return list((await session.scalars(stmt)).all())


async def list_documents_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[DatasetDocument], int]:
    """Return paginated documents for one dataset."""

    filters = [
        DatasetDocument.workspace_id == workspace_id,
        DatasetDocument.dataset_id == dataset_id,
    ]
    if keyword and keyword.strip():
        filters.append(DatasetDocument.name.ilike(f"%{keyword.strip()}%"))
    count_stmt = select(func.count()).select_from(DatasetDocument).where(*filters)
    total = int((await session.scalar(count_stmt)) or 0)
    offset = (page - 1) * page_size
    rows_stmt = (
        select(DatasetDocument)
        .where(*filters)
        .order_by(DatasetDocument.position.asc(), DatasetDocument.create_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list((await session.scalars(rows_stmt)).all())
    return rows, total


async def sum_segment_hit_counts_by_document_ids(
    session: AsyncSession,
    *,
    document_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Return total segment hit counts keyed by document id."""

    if not document_ids:
        return {}
    stmt = (
        select(
            DatasetDocumentSegment.document_id,
            func.coalesce(func.sum(DatasetDocumentSegment.hit_count), 0),
        )
        .where(DatasetDocumentSegment.document_id.in_(document_ids))
        .group_by(DatasetDocumentSegment.document_id)
    )
    rows = await session.execute(stmt)
    return {document_id: int(total or 0) for document_id, total in rows.all()}


async def get_document_for_dataset(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> DatasetDocument | None:
    """Load one document scoped to workspace and dataset."""

    stmt = select(DatasetDocument).where(
        DatasetDocument.id == document_id,
        DatasetDocument.workspace_id == workspace_id,
        DatasetDocument.dataset_id == dataset_id,
    )
    return await session.scalar(stmt)


async def list_segments_page(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    page: int,
    page_size: int,
    keyword: str | None = None,
) -> tuple[list[DatasetDocumentSegment], int]:
    """Return paginated segments for one document."""

    filters = [
        DatasetDocumentSegment.dataset_id == dataset_id,
        DatasetDocumentSegment.document_id == document_id,
    ]
    if keyword and keyword.strip():
        filters.append(DatasetDocumentSegment.content.ilike(f"%{keyword.strip()}%"))
    count_stmt = select(func.count()).select_from(DatasetDocumentSegment).where(*filters)
    total = int((await session.scalar(count_stmt)) or 0)
    offset = (page - 1) * page_size
    rows_stmt = (
        select(DatasetDocumentSegment)
        .where(*filters)
        .order_by(DatasetDocumentSegment.position.asc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list((await session.scalars(rows_stmt)).all())
    return rows, total


async def get_segment_for_document(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> DatasetDocumentSegment | None:
    """Load one segment scoped to dataset and document."""

    stmt = select(DatasetDocumentSegment).where(
        DatasetDocumentSegment.id == segment_id,
        DatasetDocumentSegment.dataset_id == dataset_id,
        DatasetDocumentSegment.document_id == document_id,
    )
    return await session.scalar(stmt)


async def max_segment_position(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> int:
    """Return highest segment position within one document."""

    stmt = select(func.max(DatasetDocumentSegment.position)).where(
        DatasetDocumentSegment.dataset_id == dataset_id,
        DatasetDocumentSegment.document_id == document_id,
    )
    return int((await session.scalar(stmt)) or 0)


async def get_child_chunks_by_node_ids(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    node_ids: list[str],
) -> list:
    """Load child chunks by vector node ids."""

    from app.dataset.domain.db.models import DatasetChildChunk

    if not node_ids:
        return []
    stmt = select(DatasetChildChunk).where(
        DatasetChildChunk.dataset_id == dataset_id,
        DatasetChildChunk.index_node_id.in_(node_ids),
    )
    return list((await session.scalars(stmt)).all())


async def list_child_chunks_for_segment(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> list:
    """Return child chunks belonging to one parent segment."""

    from app.dataset.domain.db.models import DatasetChildChunk

    stmt = (
        select(DatasetChildChunk)
        .where(
            DatasetChildChunk.dataset_id == dataset_id,
            DatasetChildChunk.document_id == document_id,
            DatasetChildChunk.segment_id == segment_id,
        )
        .order_by(DatasetChildChunk.position.asc())
    )
    return list((await session.scalars(stmt)).all())


async def get_child_chunk_for_segment(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    child_chunk_id: uuid.UUID,
):
    """Load one child chunk scoped to dataset, document, and parent segment."""

    from app.dataset.domain.db.models import DatasetChildChunk

    stmt = select(DatasetChildChunk).where(
        DatasetChildChunk.id == child_chunk_id,
        DatasetChildChunk.dataset_id == dataset_id,
        DatasetChildChunk.document_id == document_id,
        DatasetChildChunk.segment_id == segment_id,
    )
    return await session.scalar(stmt)


async def max_child_chunk_position(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
) -> int:
    """Return highest child chunk position under one parent segment."""

    from app.dataset.domain.db.models import DatasetChildChunk

    stmt = select(func.max(DatasetChildChunk.position)).where(
        DatasetChildChunk.dataset_id == dataset_id,
        DatasetChildChunk.document_id == document_id,
        DatasetChildChunk.segment_id == segment_id,
    )
    return int((await session.scalar(stmt)) or 0)


async def count_segments_for_document(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> tuple[int, int]:
    """Return (total_segments, completed_segments) for one document."""

    from app.dataset.domain.constants import INDEXING_STATUS_COMPLETED

    base_filters = (
        DatasetDocumentSegment.dataset_id == dataset_id,
        DatasetDocumentSegment.document_id == document_id,
    )
    total = int(
        (await session.scalar(select(func.count()).select_from(DatasetDocumentSegment).where(*base_filters)))
        or 0
    )
    completed = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(DatasetDocumentSegment)
                .where(*base_filters, DatasetDocumentSegment.status == INDEXING_STATUS_COMPLETED)
            )
        )
        or 0
    )
    return total, completed


async def count_child_chunks_for_segments(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    segment_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Count child chunks grouped by parent segment id."""

    from app.dataset.domain.db.models import DatasetChildChunk

    if not segment_ids:
        return {}
    stmt = (
        select(DatasetChildChunk.segment_id, func.count())
        .where(
            DatasetChildChunk.dataset_id == dataset_id,
            DatasetChildChunk.segment_id.in_(segment_ids),
        )
        .group_by(DatasetChildChunk.segment_id)
    )
    rows = list((await session.execute(stmt)).all())
    return {segment_id: int(count) for segment_id, count in rows}


async def get_segments_by_ids(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    segment_ids: list[uuid.UUID],
) -> dict[uuid.UUID, DatasetDocumentSegment]:
    """Load parent segments keyed by id."""

    if not segment_ids:
        return {}
    stmt = select(DatasetDocumentSegment).where(
        DatasetDocumentSegment.dataset_id == dataset_id,
        DatasetDocumentSegment.id.in_(segment_ids),
    )
    rows = list((await session.scalars(stmt)).all())
    return {row.id: row for row in rows}


async def get_segments_by_node_ids(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    node_ids: list[str],
) -> list[DatasetDocumentSegment]:
    """Load segments by vector node ids."""

    if not node_ids:
        return []
    stmt = select(DatasetDocumentSegment).where(
        DatasetDocumentSegment.dataset_id == dataset_id,
        DatasetDocumentSegment.index_node_id.in_(node_ids),
    )
    return list((await session.scalars(stmt)).all())


async def get_documents_by_ids(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_ids: list[uuid.UUID],
) -> dict[uuid.UUID, DatasetDocument]:
    """Load documents keyed by id."""

    if not document_ids:
        return {}
    stmt = select(DatasetDocument).where(
        DatasetDocument.dataset_id == dataset_id,
        DatasetDocument.id.in_(document_ids),
    )
    rows = list((await session.scalars(stmt)).all())
    return {row.id: row for row in rows}


async def list_queries_page(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list, int]:
    """Return paginated hit-testing query history."""

    from app.dataset.domain.db.models import DatasetQuery

    filters = [DatasetQuery.dataset_id == dataset_id]
    count_stmt = select(func.count()).select_from(DatasetQuery).where(*filters)
    total = int((await session.scalar(count_stmt)) or 0)
    offset = (page - 1) * page_size
    rows_stmt = (
        select(DatasetQuery)
        .where(*filters)
        .order_by(DatasetQuery.create_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list((await session.scalars(rows_stmt)).all())
    return rows, total
