"""In-memory list filter matches ACL (no DB)."""

from uuid import uuid4

from app.core.domain.identity.models import MembershipRole
from app.graph_kb.domain.acl import GraphAclActor, GraphAclSubject, can_view_graph
from app.graph_kb.domain.constants import PERMISSION_ALL_TEAM_MEMBERS, PERMISSION_ONLY_ME
from app.graph_kb.service.graph_service import filter_graphs_for_actor


class _Row:
    def __init__(self, permission: str, created_by):
        self.id = uuid4()
        self.workspace_id = uuid4()
        self.permission = permission
        self.created_by = created_by


def test_filter_hides_only_me_from_other_member() -> None:
    owner = uuid4()
    other = uuid4()
    rows = [_Row(PERMISSION_ONLY_ME, owner), _Row(PERMISSION_ALL_TEAM_MEMBERS, owner)]
    actor = GraphAclActor(
        user_id=other, is_super_admin=False, workspace_role=MembershipRole.member
    )
    visible = filter_graphs_for_actor(rows, actor=actor, members_by_graph={})
    assert [r.permission for r in visible] == [PERMISSION_ALL_TEAM_MEMBERS]
