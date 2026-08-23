"""GraphKB CRUD, ACL-aware list filter, and member replacement."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.graph_kb.domain.acl import (
    GraphAclActor,
    GraphAclSubject,
    can_view_graph,
    raise_if_cannot_manage,
    raise_if_cannot_view,
)
from app.graph_kb.domain.constants import ENGINES, PERMISSIONS, STATUS_EMPTY
from app.graph_kb.domain.db.models import GraphKb
from app.graph_kb.infrastructure import repository as repo
from app.graph_kb.service.actor import actor_from_user

__all__ = [
    "actor_from_user",
    "create_graph",
    "filter_graphs_for_actor",
    "get_graph_for_manage",
    "get_graph_for_view",
    "list_graphs_for_actor",
    "patch_graph",
    "replace_members",
]


def _subject_from_row(row: GraphKb) -> GraphAclSubject:
    """Map a GraphKb ORM row to an ACL subject."""

    return GraphAclSubject(
        graph_id=row.id,
        workspace_id=row.workspace_id,
        permission=row.permission,
        created_by=row.created_by,
    )


def filter_graphs_for_actor(
    rows: Sequence[Any],
    *,
    actor: GraphAclActor,
    members_by_graph: dict[uuid.UUID, set[uuid.UUID]],
) -> list[Any]:
    """Return rows the actor may view (pure; no DB).

    Each row must expose ``id``, ``workspace_id``, ``permission``, and ``created_by``.
    Admin / super-admin pass via ``can_view_graph``; members are ACL-filtered.
    """

    visible: list[Any] = []
    for row in rows:
        subject = GraphAclSubject(
            graph_id=row.id,
            workspace_id=row.workspace_id,
            permission=row.permission,
            created_by=row.created_by,
        )
        member_ids = members_by_graph.get(row.id, set())
        if can_view_graph(actor=actor, graph=subject, member_ids=member_ids):
            visible.append(row)
    return visible


async def create_graph(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    engine: str,
    permission: str,
    llm_model: str | None = None,
    llm_model_provider: str | None = None,
    embedding_model: str | None = None,
    embedding_model_provider: str | None = None,
    description: str | None = None,
) -> GraphKb:
    """Create a graph with ``indexing_status=empty``; reject unknown engine/permission."""

    if engine not in ENGINES:
        raise AppError("graph_kb.engine_invalid", "不支持的图谱引擎。", 400)
    if permission not in PERMISSIONS:
        raise AppError("graph_kb.permission_invalid", "不支持的图谱权限。", 400)
    label = name.strip()
    if not label:
        raise AppError("graph_kb.name_required", "图谱名称不能为空。", 422)

    row = GraphKb(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=label,
        description=description,
        engine=engine,
        permission=permission,
        llm_model=llm_model,
        llm_model_provider=llm_model_provider,
        embedding_model=embedding_model,
        embedding_model_provider=embedding_model_provider,
        indexing_status=STATUS_EMPTY,
        created_by=user_id,
        updated_by=user_id,
    )
    return await repo.insert(session, row)


async def list_graphs_for_actor(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor: GraphAclActor,
    page: int,
    page_size: int,
    name: str | None = None,
    mine_only: bool = False,
) -> tuple[list[GraphKb], int]:
    """List graphs visible to ``actor``; ACL filter in memory then paginate."""

    rows = await repo.list_by_workspace(session, workspace_id=workspace_id, name=name)
    members_by_graph = await repo.list_members_by_graph_ids(
        session,
        workspace_id=workspace_id,
        graph_ids=[row.id for row in rows],
    )
    visible = filter_graphs_for_actor(rows, actor=actor, members_by_graph=members_by_graph)
    if mine_only:
        visible = [row for row in visible if row.created_by == actor.user_id]
    total = len(visible)
    offset = max(page - 1, 0) * page_size
    return visible[offset : offset + page_size], total


async def get_graph_for_view(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
) -> GraphKb:
    """Load a graph the actor may view, or raise 404."""

    row = await repo.get_by_id(session, workspace_id=workspace_id, graph_id=graph_id)
    if row is None:
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)
    member_ids = await repo.list_member_user_ids(
        session, workspace_id=workspace_id, graph_id=graph_id
    )
    raise_if_cannot_view(actor=actor, graph=_subject_from_row(row), member_ids=member_ids)
    return row


async def get_graph_for_manage(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
) -> GraphKb:
    """Load a graph the actor may manage, or raise 404."""

    row = await repo.get_by_id(session, workspace_id=workspace_id, graph_id=graph_id)
    if row is None:
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)
    raise_if_cannot_manage(actor=actor, graph=_subject_from_row(row))
    return row


async def patch_graph(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    patch: dict[str, Any],
) -> GraphKb:
    """Patch mutable graph fields; reject engine changes with 400."""

    row = await get_graph_for_manage(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    if "engine" in patch and patch["engine"] is not None:
        if str(patch["engine"]) != row.engine:
            raise AppError(
                "graph_kb.engine_immutable",
                "图谱引擎创建后不可修改。",
                400,
            )

    fields: dict[str, Any] = {}
    if "name" in patch and patch["name"] is not None:
        label = str(patch["name"]).strip()
        if not label:
            raise AppError("graph_kb.name_required", "图谱名称不能为空。", 422)
        fields["name"] = label
    if "description" in patch:
        fields["description"] = patch["description"]
    if "permission" in patch and patch["permission"] is not None:
        permission = str(patch["permission"])
        if permission not in PERMISSIONS:
            raise AppError("graph_kb.permission_invalid", "不支持的图谱权限。", 400)
        fields["permission"] = permission
    for key in (
        "llm_model",
        "llm_model_provider",
        "embedding_model",
        "embedding_model_provider",
    ):
        if key in patch:
            fields[key] = patch[key]

    if not fields:
        return row
    return await repo.update_fields(session, row, fields, updated_by=actor.user_id)


async def replace_members(
    session: AsyncSession,
    *,
    graph_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_ids: Iterable[uuid.UUID],
    created_by: uuid.UUID,
) -> None:
    """Replace ``graph_kb_member`` rows for a graph (caller enforces manage ACL)."""

    await repo.replace_members(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        user_ids=user_ids,
        created_by=created_by,
    )
