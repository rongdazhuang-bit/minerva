"""GraphKB query: readiness gate, engine call, and history persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.graph_kb.domain.acl import GraphAclActor
from app.graph_kb.domain.constants import STATUS_COMPLETED
from app.graph_kb.domain.db.models import (
    GraphKbCommunity,
    GraphKbEntity,
    GraphKbQuery,
    GraphKbRelation,
)
from app.graph_kb.engine.factory import create_engine_client
from app.graph_kb.engine.modes import map_query_mode
from app.graph_kb.engine.types import WorkerQueryRequest, WorkerQueryResult
from app.graph_kb.service import graph_service as graph_svc
from app.pagination import DEFAULT_PAGE_SIZE


def assert_ready_for_query(indexing_status: str) -> None:
    """Raise ``graph_kb.not_ready`` (409) unless the graph index is completed."""

    if indexing_status != STATUS_COMPLETED:
        raise AppError(
            "graph_kb.not_ready",
            "图谱尚未完成索引，暂不可查询。",
            409,
        )


async def query_graph(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    query: str,
    mode: str,
    top_k: int = 5,
) -> WorkerQueryResult:
    """Run a Worker query when the graph is ready; persist a ``graph_kb_query`` row.

    Propagates Worker ``AppError`` (including 503) without rewriting to 200.
    """

    graph = await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    assert_ready_for_query(graph.indexing_status)
    resolved_mode = map_query_mode(graph.engine, mode)
    text = (query or "").strip()
    if not text:
        raise AppError("graph_kb.query_required", "查询内容不能为空。", 400)

    client = create_engine_client()
    result = await client.query(
        WorkerQueryRequest(
            workspace_id=workspace_id,
            graph_id=graph_id,
            engine=graph.engine,
            query=text,
            mode=resolved_mode,
            top_k=top_k,
        )
    )
    row = GraphKbQuery(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        graph_id=graph_id,
        query=text,
        mode=resolved_mode,
        answer=result.answer,
        citations=list(result.citations),
        created_by=actor.user_id,
    )
    session.add(row)
    await session.flush()
    return result


async def list_queries(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[GraphKbQuery], int]:
    """Return paginated Q&A history for a graph the actor may view."""

    await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    filters = [
        GraphKbQuery.workspace_id == workspace_id,
        GraphKbQuery.graph_id == graph_id,
    ]
    total = int(
        await session.scalar(select(func.count()).select_from(GraphKbQuery).where(*filters))
        or 0
    )
    offset = max(page - 1, 0) * page_size
    rows = list(
        (
            await session.scalars(
                select(GraphKbQuery)
                .where(*filters)
                .order_by(GraphKbQuery.create_at.desc().nullslast())
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    return rows, total


async def list_entities(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    name: str | None = None,
    entity_type: str | None = None,
) -> tuple[list[GraphKbEntity], int]:
    """Paginate entity projections; optional name / type filters."""

    await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    filters = [
        GraphKbEntity.workspace_id == workspace_id,
        GraphKbEntity.graph_id == graph_id,
    ]
    if name and name.strip():
        filters.append(GraphKbEntity.name.ilike(f"%{name.strip()}%"))
    if entity_type and entity_type.strip():
        filters.append(GraphKbEntity.entity_type == entity_type.strip())
    total = int(
        await session.scalar(select(func.count()).select_from(GraphKbEntity).where(*filters))
        or 0
    )
    offset = max(page - 1, 0) * page_size
    rows = list(
        (
            await session.scalars(
                select(GraphKbEntity)
                .where(*filters)
                .order_by(GraphKbEntity.name.asc())
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    return rows, total


async def list_relations(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[GraphKbRelation], int]:
    """Paginate relation projections for a viewable graph."""

    await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    filters = [
        GraphKbRelation.workspace_id == workspace_id,
        GraphKbRelation.graph_id == graph_id,
    ]
    total = int(
        await session.scalar(select(func.count()).select_from(GraphKbRelation).where(*filters))
        or 0
    )
    offset = max(page - 1, 0) * page_size
    rows = list(
        (
            await session.scalars(
                select(GraphKbRelation)
                .where(*filters)
                .order_by(GraphKbRelation.create_at.desc().nullslast())
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    return rows, total


async def list_summaries(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[GraphKbCommunity], int]:
    """Paginate community / topic summary projections."""

    await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    filters = [
        GraphKbCommunity.workspace_id == workspace_id,
        GraphKbCommunity.graph_id == graph_id,
    ]
    total = int(
        await session.scalar(select(func.count()).select_from(GraphKbCommunity).where(*filters))
        or 0
    )
    offset = max(page - 1, 0) * page_size
    rows = list(
        (
            await session.scalars(
                select(GraphKbCommunity)
                .where(*filters)
                .order_by(
                    GraphKbCommunity.level.asc().nullslast(),
                    GraphKbCommunity.title.asc().nullslast(),
                )
                .offset(offset)
                .limit(page_size)
            )
        ).all()
    )
    return rows, total
