"""Tests for workspace-scoped get_actor_capabilities delegation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.domain.identity.models import MembershipRole
from app.sys.user.service import user_service as svc


@pytest.mark.asyncio
async def test_get_actor_capabilities_delegates_scope_flags_to_build_user_list():
    tenant_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_tenant = MagicMock()
    mock_tenant.name = "Acme"
    mock_session.get.return_value = mock_tenant

    with (
        patch.object(svc.repo, "get_tenant_id_for_workspace", AsyncMock(return_value=tenant_id)),
        patch.object(svc.auth_repo, "is_tenant_admin", AsyncMock(return_value=True)),
        patch.object(
            svc,
            "find_workspace_role_for_user",
            AsyncMock(return_value=MembershipRole.admin),
        ),
    ):
        caps = await svc.get_actor_capabilities(
            mock_session,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            actor_is_super_admin=False,
        )

    assert caps["can_pick_tenant"] is False
    assert caps["can_pick_workspace"] is True
    assert caps["fixed_tenant_id"] == tenant_id
    assert caps["fixed_tenant_name"] == "Acme"
    assert caps["can_pick_tenant_workspace"] is False
    assert "admin" in caps["assignable_membership_roles"]


@pytest.mark.asyncio
async def test_get_actor_capabilities_super_admin_can_pick_tenant():
    tenant_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_tenant = MagicMock()
    mock_tenant.name = "Platform"
    mock_session.get.return_value = mock_tenant

    with (
        patch.object(svc.repo, "get_tenant_id_for_workspace", AsyncMock(return_value=tenant_id)),
        patch.object(svc.auth_repo, "is_tenant_admin", AsyncMock(return_value=False)),
        patch.object(
            svc,
            "find_workspace_role_for_user",
            AsyncMock(return_value=MembershipRole.admin),
        ),
    ):
        caps = await svc.get_actor_capabilities(
            mock_session,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            actor_is_super_admin=True,
        )

    assert caps["can_pick_tenant"] is True
    assert caps["can_pick_workspace"] is True
    assert caps["fixed_tenant_id"] is None
    assert caps["default_tenant_id"] == tenant_id
    assert caps["can_pick_tenant_workspace"] is True
