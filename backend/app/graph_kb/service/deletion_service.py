"""Application-layer cascade delete for GraphKB tables (no DB foreign keys)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph_kb.domain.db.models import (
    GraphKb,
    GraphKbCommunity,
    GraphKbDocument,
    GraphKbEntity,
    GraphKbJob,
    GraphKbMember,
    GraphKbQuery,
    GraphKbRelation,
)


async def delete_graph_sql(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
) -> None:
    """Delete graph dependent rows then the graph itself (spec §5.7 sync order).

    Order: query → community → relation → entity → job → document → member → graph_kb.
    Every delete is scoped by both ``workspace_id`` and ``graph_id``. Does not touch
    object storage or Worker namespaces (async cleanup is separate).
    """

    for model in (
        GraphKbQuery,
        GraphKbCommunity,
        GraphKbRelation,
        GraphKbEntity,
        GraphKbJob,
        GraphKbDocument,
        GraphKbMember,
    ):
        await session.execute(
            delete(model).where(
                model.workspace_id == workspace_id,
                model.graph_id == graph_id,
            )
        )
    await session.execute(
        delete(GraphKb).where(
            GraphKb.id == graph_id,
            GraphKb.workspace_id == workspace_id,
        )
    )


async def enqueue_cleanup(
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    engine: str = "",
    user_id: uuid.UUID | None = None,
    **_kwargs: Any,
) -> None:
    """Enqueue Worker + local-file cleanup after ``delete_graph_sql`` has committed."""

    from app.graph_kb.service.cleanup_service import enqueue_cleanup as enqueue_cleanup_job

    await enqueue_cleanup_job(
        workspace_id=workspace_id,
        graph_id=graph_id,
        engine=engine or str(_kwargs.get("engine") or ""),
        user_id=user_id,
    )
