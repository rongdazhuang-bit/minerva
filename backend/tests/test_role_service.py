"""Unit tests for role service helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.domain.identity.models import Workspace
from app.exceptions import AppError
from app.sys.role.infrastructure import repository as repo
from app.sys.role.service import role_service as svc


@pytest.mark.asyncio
async def test_validate_workspace_in_tenant_raises_when_mismatch(
    db_session: AsyncMock,
) -> None:
    """Workspace must belong to the path tenant."""

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    workspace_id = uuid.uuid4()
    db_session.get = AsyncMock(
        return_value=Workspace(
            id=workspace_id,
            tenant_id=tenant_a,
            name="Test Workspace",
            slug="test-workspace",
        )
    )

    with pytest.raises(AppError) as exc_info:
        await repo.validate_workspace_in_tenant(
            db_session,
            tenant_id=tenant_b,
            workspace_id=workspace_id,
        )

    assert exc_info.value.code == "role.workspace_invalid"
    assert exc_info.value.status_code == 400


def test_build_role_capabilities_super_admin() -> None:
    """Super admin can pick tenant and workspace; defaults are all/null."""

    out = svc.build_role_capabilities(
        is_super_admin=True,
        is_tenant_admin=False,
        jwt_tenant_id=None,
        jwt_tenant_name=None,
    )
    assert out["can_pick_tenant"] is True
    assert out["can_pick_workspace"] is True
    assert out["default_filter_tenant_id"] is None
    assert out["default_filter_workspace_id"] is None


def test_build_role_capabilities_tenant_admin() -> None:
    """Tenant admin has fixed tenant and all-workspace default filter."""

    tid = uuid.uuid4()
    out = svc.build_role_capabilities(
        is_super_admin=False,
        is_tenant_admin=True,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
    )
    assert out["can_pick_tenant"] is False
    assert out["fixed_tenant_id"] == tid
    assert out["default_filter_tenant_id"] == tid
    assert out["default_filter_workspace_id"] is None
