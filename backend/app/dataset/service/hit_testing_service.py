"""Hit testing orchestration for knowledge bases."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.db.models import DatasetQuery
from app.dataset.rag.retrieval.retrieval_service import retrieve
from app.dataset.service.dataset_service import require_dataset


async def run_hit_testing(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    retrieval_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute retrieval, persist query history, and return records."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    records = await retrieve(
        session,
        dataset=dataset,
        query=query,
        retrieval_model=retrieval_model,
    )
    session.add(
        DatasetQuery(
            id=uuid.uuid4(),
            dataset_id=dataset.id,
            content=query.strip(),
            source="hit_testing",
            created_by_role="account",
            created_by=user_id,
        )
    )
    await session.commit()
    return {"query": query.strip(), "records": records}


async def list_query_history(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    """List prior hit-testing queries for one dataset."""

    await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    from app.dataset.infrastructure import repository as repo

    rows, total = await repo.list_queries_page(
        session,
        dataset_id=dataset_id,
        page=page,
        page_size=page_size,
    )
    items = [
        {
            "id": row.id,
            "content": row.content,
            "source": row.source,
            "create_at": row.create_at,
        }
        for row in rows
    ]
    return items, total
