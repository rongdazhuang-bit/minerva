"""Read/write queries for graph_kb and graph_kb_member tables."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph_kb.domain.db.models import GraphKb, GraphKbMember


async def insert(session: AsyncSession, row: GraphKb) -> GraphKb:
    """Persist a new graph row and refresh generated columns."""

    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_by_id(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
) -> GraphKb | None:
    """Load one graph scoped to ``workspace_id``."""

    stmt = select(GraphKb).where(
        GraphKb.id == graph_id,
        GraphKb.workspace_id == workspace_id,
    )
    return await session.scalar(stmt)


async def list_by_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str | None = None,
) -> list[GraphKb]:
    """Return all graphs in a workspace, optionally filtered by name ILIKE."""

    filters = [GraphKb.workspace_id == workspace_id]
    if name and name.strip():
        filters.append(GraphKb.name.ilike(f"%{name.strip()}%"))
    stmt = (
        select(GraphKb)
        .where(*filters)
        .order_by(GraphKb.create_at.desc().nullslast(), GraphKb.name.asc())
    )
    return list((await session.scalars(stmt)).all())


async def list_member_user_ids(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Return user ids listed in ``graph_kb_member`` for one graph."""

    stmt = select(GraphKbMember.user_id).where(
        GraphKbMember.workspace_id == workspace_id,
        GraphKbMember.graph_id == graph_id,
    )
    return set((await session.scalars(stmt)).all())


async def list_members_by_graph_ids(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Batch-load member user ids keyed by graph id within a workspace."""

    if not graph_ids:
        return {}
    stmt = select(GraphKbMember.graph_id, GraphKbMember.user_id).where(
        GraphKbMember.workspace_id == workspace_id,
        GraphKbMember.graph_id.in_(list(graph_ids)),
    )
    result: dict[uuid.UUID, set[uuid.UUID]] = {gid: set() for gid in graph_ids}
    for graph_id, user_id in (await session.execute(stmt)).all():
        result.setdefault(graph_id, set()).add(user_id)
    return result


async def replace_members(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    user_ids: Iterable[uuid.UUID],
    created_by: uuid.UUID,
) -> None:
    """Replace partial-member rows for a graph (delete then insert)."""

    await session.execute(
        delete(GraphKbMember).where(
            GraphKbMember.workspace_id == workspace_id,
            GraphKbMember.graph_id == graph_id,
        )
    )
    seen: set[uuid.UUID] = set()
    for user_id in user_ids:
        if user_id in seen:
            continue
        seen.add(user_id)
        session.add(
            GraphKbMember(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                graph_id=graph_id,
                user_id=user_id,
                created_by=created_by,
            )
        )
    await session.flush()


async def update_fields(
    session: AsyncSession,
    row: GraphKb,
    fields: dict[str, Any],
    *,
    updated_by: uuid.UUID,
) -> GraphKb:
    """Apply allowed column updates on an already-loaded graph row."""

    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_by = updated_by
    row.update_at = datetime.now(tz=UTC)
    await session.flush()
    await session.refresh(row)
    return row
