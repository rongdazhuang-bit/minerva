"""Build GraphKB API response models from ORM rows."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.graph_kb.api.schemas import GraphKbOut
from app.graph_kb.domain.db.models import GraphKb
from app.graph_kb.infrastructure import repository as repo


async def graph_kb_out_list(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rows: list[GraphKb],
) -> list[GraphKbOut]:
    """Map graph rows to ``GraphKbOut``, batch-loading ``member_user_ids``."""

    if not rows:
        return []
    member_map = await repo.list_members_by_graph_ids(
        session,
        workspace_id=workspace_id,
        graph_ids=[row.id for row in rows],
    )
    items: list[GraphKbOut] = []
    for row in rows:
        payload = GraphKbOut.model_validate(row)
        member_ids = sorted(member_map.get(row.id, set()), key=str)
        items.append(payload.model_copy(update={"member_user_ids": member_ids}))
    return items


async def graph_kb_out_one(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    row: GraphKb,
) -> GraphKbOut:
    """Build one ``GraphKbOut`` including member ids for detail/create/patch responses."""

    items = await graph_kb_out_list(session, workspace_id=workspace_id, rows=[row])
    return items[0]
