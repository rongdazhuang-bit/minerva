"""HTTP routes for workspace graph knowledge bases."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.graph_kb.api.deps import require_graph_kb_workspace
from app.graph_kb.api.schemas import (
    GraphKbCreateIn,
    GraphKbListPageOut,
    GraphKbOut,
    GraphKbPatchIn,
)
from app.graph_kb.domain.db.models import GraphKb
from app.graph_kb.infrastructure import repository as repo
from app.graph_kb.service import deletion_service
from app.graph_kb.service import graph_service as graph_svc
from app.graph_kb.service.actor import actor_from_user
from app.pagination import DEFAULT_PAGE_SIZE

router = APIRouter(prefix="/workspaces/{workspace_id}/graph-kbs", tags=["graph-kbs"])


async def _graph_out(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    row: GraphKb,
) -> GraphKbOut:
    """Build ``GraphKbOut`` including current member user ids."""

    member_ids = await repo.list_member_user_ids(
        session, workspace_id=workspace_id, graph_id=row.id
    )
    payload = GraphKbOut.model_validate(row)
    return payload.model_copy(update={"member_user_ids": sorted(member_ids, key=str)})


@router.get("", response_model=GraphKbListPageOut)
async def list_graph_kbs(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    name: str | None = Query(default=None, description="图谱名称关键词"),
    mine_only: bool = Query(default=False, description="仅返回当前用户创建的图谱"),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbListPageOut:
    """List graphs visible to the caller with optional name / mine filters."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    rows, total = await graph_svc.list_graphs_for_actor(
        session,
        workspace_id=workspace_id,
        actor=actor,
        page=page,
        page_size=page_size,
        name=name,
        mine_only=mine_only,
    )
    items = [GraphKbOut.model_validate(row) for row in rows]
    return GraphKbListPageOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=GraphKbOut, status_code=201)
async def create_graph_kb(
    workspace_id: uuid.UUID,
    body: GraphKbCreateIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbOut:
    """Create an empty graph; empty ``member_user_ids`` is allowed for partial_members."""

    row = await graph_svc.create_graph(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
        name=body.name,
        engine=body.engine,
        permission=body.permission,
        llm_model=body.llm_model,
        llm_model_provider=body.llm_model_provider,
        embedding_model=body.embedding_model,
        embedding_model_provider=body.embedding_model_provider,
        description=body.description,
    )
    if body.member_user_ids:
        await graph_svc.replace_members(
            session,
            graph_id=row.id,
            workspace_id=workspace_id,
            user_ids=body.member_user_ids,
            created_by=user.id,
        )
    await session.commit()
    await session.refresh(row)
    return await _graph_out(session, workspace_id=workspace_id, row=row)


@router.get("/{graph_id}", response_model=GraphKbOut)
async def get_graph_kb(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbOut:
    """Return one graph the caller may view."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    row = await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    return await _graph_out(session, workspace_id=workspace_id, row=row)


@router.patch("/{graph_id}", response_model=GraphKbOut)
async def patch_graph_kb(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    body: GraphKbPatchIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbOut:
    """Update mutable settings and optionally replace partial members."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    patch = body.model_dump(exclude_unset=True)
    member_ids = patch.pop("member_user_ids", None)
    row = await graph_svc.patch_graph(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        patch=patch,
    )
    if member_ids is not None:
        await graph_svc.replace_members(
            session,
            graph_id=row.id,
            workspace_id=workspace_id,
            user_ids=member_ids,
            created_by=user.id,
        )
    await session.commit()
    await session.refresh(row)
    return await _graph_out(session, workspace_id=workspace_id, row=row)


@router.delete("/{graph_id}", status_code=204)
async def delete_graph_kb(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete graph SQL rows synchronously; enqueue async cleanup (stub)."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    await graph_svc.get_graph_for_manage(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    await deletion_service.delete_graph_sql(
        session, workspace_id=workspace_id, graph_id=graph_id
    )
    await session.commit()
    await deletion_service.enqueue_cleanup(workspace_id=workspace_id, graph_id=graph_id)
