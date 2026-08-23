"""GraphKB ACL: super-admin, workspace admin, and member permissions."""

from uuid import uuid4

import pytest

from app.core.domain.identity.models import MembershipRole
from app.exceptions import AppError
from app.graph_kb.domain.acl import (
    GraphAclActor,
    GraphAclSubject,
    can_manage_graph,
    can_view_graph,
    raise_if_cannot_manage,
    raise_if_cannot_view,
)
from app.graph_kb.domain.constants import (
    PERMISSION_ALL_TEAM_MEMBERS,
    PERMISSION_ONLY_ME,
    PERMISSION_PARTIAL_MEMBERS,
)


def _subject(permission: str, created_by):
    return GraphAclSubject(
        graph_id=uuid4(),
        workspace_id=uuid4(),
        permission=permission,
        created_by=created_by,
    )


def test_super_admin_views_only_me_graph() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=True, workspace_role=None
    )
    assert can_view_graph(actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner), member_ids=set())


def test_workspace_admin_views_only_me_of_other_user() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.admin
    )
    assert can_view_graph(actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner), member_ids=set())


def test_member_cannot_view_others_only_me() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert not can_view_graph(
        actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner), member_ids=set()
    )


def test_member_views_all_team_members() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert can_view_graph(
        actor=actor,
        graph=_subject(PERMISSION_ALL_TEAM_MEMBERS, uuid4()),
        member_ids=set(),
    )


def test_partial_member_can_view() -> None:
    user = uuid4()
    actor = GraphAclActor(
        user_id=user, is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert can_view_graph(
        actor=actor,
        graph=_subject(PERMISSION_PARTIAL_MEMBERS, uuid4()),
        member_ids={user},
    )


def test_non_member_cannot_view() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=None
    )
    assert not can_view_graph(
        actor=actor,
        graph=_subject(PERMISSION_ALL_TEAM_MEMBERS, uuid4()),
        member_ids=set(),
    )


def test_creator_can_manage_own_graph() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=owner, is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert can_manage_graph(actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner))


def test_member_cannot_manage_others_graph() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert not can_manage_graph(actor=actor, graph=_subject(PERMISSION_ALL_TEAM_MEMBERS, uuid4()))


def test_raise_if_cannot_view_is_404() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    with pytest.raises(AppError) as exc:
        raise_if_cannot_view(
            actor=actor,
            graph=_subject(PERMISSION_ONLY_ME, uuid4()),
            member_ids=set(),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "graph_kb.not_found"


def test_raise_if_cannot_manage_is_404() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    with pytest.raises(AppError) as exc:
        raise_if_cannot_manage(
            actor=actor,
            graph=_subject(PERMISSION_ALL_TEAM_MEMBERS, uuid4()),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "graph_kb.not_found"
