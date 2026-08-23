"""Workspace-shared graph ACL: super-admin, admin overview, member visibility."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.domain.identity.models import MembershipRole
from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    PERMISSION_ALL_TEAM_MEMBERS,
    PERMISSION_ONLY_ME,
    PERMISSION_PARTIAL_MEMBERS,
)


@dataclass(frozen=True)
class GraphAclActor:
    """Caller identity for a GraphKB authorization decision."""

    user_id: UUID
    is_super_admin: bool
    workspace_role: MembershipRole | None


@dataclass(frozen=True)
class GraphAclSubject:
    """Graph fields required to evaluate ACL."""

    graph_id: UUID
    workspace_id: UUID
    permission: str
    created_by: UUID


def can_view_graph(
    *,
    actor: GraphAclActor,
    graph: GraphAclSubject,
    member_ids: set[UUID],
) -> bool:
    """Return whether actor may read the graph (list, browse, query)."""

    if actor.is_super_admin:
        return True
    if actor.workspace_role is None:
        return False
    if actor.workspace_role == MembershipRole.admin:
        return True
    if graph.created_by == actor.user_id:
        return True
    if graph.permission == PERMISSION_ALL_TEAM_MEMBERS:
        return True
    if graph.permission == PERMISSION_PARTIAL_MEMBERS and actor.user_id in member_ids:
        return True
    if graph.permission == PERMISSION_ONLY_ME:
        return False
    return False


def can_manage_graph(*, actor: GraphAclActor, graph: GraphAclSubject) -> bool:
    """Return whether actor may change ACL, delete, or reindex the graph."""

    if actor.is_super_admin:
        return True
    if actor.workspace_role == MembershipRole.admin:
        return True
    return graph.created_by == actor.user_id


def raise_if_cannot_view(
    *,
    actor: GraphAclActor,
    graph: GraphAclSubject,
    member_ids: set[UUID],
) -> None:
    """Raise 404 when the caller cannot view the graph."""

    if not can_view_graph(actor=actor, graph=graph, member_ids=member_ids):
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)


def raise_if_cannot_manage(*, actor: GraphAclActor, graph: GraphAclSubject) -> None:
    """Raise 404 when the caller cannot manage the graph."""

    if not can_manage_graph(actor=actor, graph=graph):
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)
