"""Service-layer isolation: cross-workspace and only_me view ACL."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.domain.identity.models import MembershipRole
from app.exceptions import AppError
from app.graph_kb.domain.acl import GraphAclActor
from app.graph_kb.domain.constants import PERMISSION_ONLY_ME
from app.graph_kb.service.graph_service import get_graph_for_view


def _graph_row(
    *,
    workspace_id,
    graph_id,
    created_by,
    permission: str = PERMISSION_ONLY_ME,
) -> SimpleNamespace:
    """Minimal GraphKb-shaped row for ``get_graph_for_view`` ACL checks."""

    return SimpleNamespace(
        id=graph_id,
        workspace_id=workspace_id,
        permission=permission,
        created_by=created_by,
    )


@pytest.mark.asyncio
async def test_other_workspace_member_cannot_view() -> None:
    """``get_by_id`` is workspace-scoped; a guessed id from another workspace is 404."""

    session = AsyncMock()
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    with patch(
        "app.graph_kb.service.graph_service.repo.get_by_id",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(AppError) as exc:
            await get_graph_for_view(
                session,
                workspace_id=uuid4(),
                graph_id=uuid4(),
                actor=actor,
            )
    assert exc.value.status_code == 404
    assert exc.value.code == "graph_kb.not_found"


@pytest.mark.asyncio
async def test_only_me_other_member_404() -> None:
    """A workspace member who is not the owner cannot view an only_me graph."""

    session = AsyncMock()
    owner = uuid4()
    row = _graph_row(
        workspace_id=uuid4(),
        graph_id=uuid4(),
        created_by=owner,
    )
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    with (
        patch(
            "app.graph_kb.service.graph_service.repo.get_by_id",
            new=AsyncMock(return_value=row),
        ),
        patch(
            "app.graph_kb.service.graph_service.repo.list_member_user_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        with pytest.raises(AppError) as exc:
            await get_graph_for_view(
                session,
                workspace_id=row.workspace_id,
                graph_id=row.id,
                actor=actor,
            )
    assert exc.value.status_code == 404
    assert exc.value.code == "graph_kb.not_found"


@pytest.mark.asyncio
async def test_admin_can_view_only_me_of_other() -> None:
    """Workspace admin may view another member's only_me graph."""

    session = AsyncMock()
    row = _graph_row(
        workspace_id=uuid4(),
        graph_id=uuid4(),
        created_by=uuid4(),
    )
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.admin
    )
    with (
        patch(
            "app.graph_kb.service.graph_service.repo.get_by_id",
            new=AsyncMock(return_value=row),
        ),
        patch(
            "app.graph_kb.service.graph_service.repo.list_member_user_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        loaded = await get_graph_for_view(
            session,
            workspace_id=row.workspace_id,
            graph_id=row.id,
            actor=actor,
        )
    assert loaded is row


@pytest.mark.asyncio
async def test_super_admin_can_view_only_me_of_other() -> None:
    """Super-admin may view another user's only_me graph without a workspace role."""

    session = AsyncMock()
    row = _graph_row(
        workspace_id=uuid4(),
        graph_id=uuid4(),
        created_by=uuid4(),
    )
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=True, workspace_role=None
    )
    with (
        patch(
            "app.graph_kb.service.graph_service.repo.get_by_id",
            new=AsyncMock(return_value=row),
        ),
        patch(
            "app.graph_kb.service.graph_service.repo.list_member_user_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        loaded = await get_graph_for_view(
            session,
            workspace_id=row.workspace_id,
            graph_id=row.id,
            actor=actor,
        )
    assert loaded is row
