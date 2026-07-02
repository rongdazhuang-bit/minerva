"""Unit tests for role service helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.domain.identity.models import Workspace
from app.exceptions import AppError
from app.sys.role.infrastructure import repository as repo


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
