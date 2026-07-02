"""Tests for tenant admin authorization on workspace-users routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.exceptions import AppError
from app.sys.tenant.api import deps as tenant_deps
from app.sys.user.service import user_service as user_svc


@pytest.mark.asyncio
async def test_require_tenant_admin_allows_super_admin():
    tenant_id = uuid.uuid4()
    user = MagicMock()
    user.is_super_admin = True
    user.id = uuid.uuid4()

    result = await tenant_deps.require_tenant_admin(
        tenant_id=tenant_id,
        user=user,
        cred=None,
        session=AsyncMock(),
    )
    assert result is user


@pytest.mark.asyncio
async def test_require_tenant_admin_denies_wrong_tenant_context():
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    user = MagicMock()
    user.is_super_admin = False
    user.id = uuid.uuid4()

    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    mock_ctx = MagicMock()
    mock_ctx.tenant_id = other_tenant_id

    with (
        patch.object(tenant_deps, "_decode_access_payload", return_value={}),
        patch.object(
            tenant_deps,
            "parse_uuid_claim",
            side_effect=lambda _p, k: other_tenant_id if k == "tid" else None,
        ),
        patch.object(
            tenant_deps, "build_permission_context", AsyncMock(return_value=mock_ctx)
        ),
    ):
        with pytest.raises(AppError) as exc_info:
            await tenant_deps.require_tenant_admin(
                tenant_id=tenant_id,
                user=user,
                cred=cred,
                session=AsyncMock(),
            )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_tenant_workspace_users_page_passes_workspace_filter():
    tenant_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_tenant = MagicMock()
    mock_tenant.name = "Acme"
    mock_session.get.return_value = mock_tenant

    with (
        patch.object(user_svc.repo, "count_tenant_workspace_members", AsyncMock(return_value=0)),
        patch.object(
            user_svc.repo, "list_tenant_workspace_members_page", AsyncMock(return_value=[])
        ),
        patch.object(user_svc, "_build_list_row", AsyncMock()) as mock_build,
        patch.object(
            user_svc, "_row_to_response_dict", AsyncMock(return_value={"id": uuid.uuid4()})
        ),
    ):
        await user_svc.list_tenant_workspace_users_page(
            mock_session,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            page=1,
            page_size=20,
            actor_is_super_admin=True,
        )
        user_svc.repo.count_tenant_workspace_members.assert_awaited_once()
        call_kwargs = user_svc.repo.count_tenant_workspace_members.await_args.kwargs
        assert call_kwargs["tenant_id"] == tenant_id
        assert call_kwargs["workspace_id"] == workspace_id
        mock_build.assert_not_called()
