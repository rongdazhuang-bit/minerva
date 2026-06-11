"""Tests for is_any_workspace_member used by global dict read gate."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.domain.identity.models import User
from app.core.domain.identity.services import is_any_workspace_member


@pytest.mark.asyncio
async def test_is_any_workspace_member_true_for_super_admin() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="sa@example.com",
            password_hash="x",
            nickname="SA",
            is_super_admin=True,
        )
    )
    assert await is_any_workspace_member(session, user_id=uid) is True
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_is_any_workspace_member_true_for_member() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="m@example.com",
            password_hash="x",
            nickname="M",
            is_super_admin=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    session.execute = AsyncMock(return_value=result)
    assert await is_any_workspace_member(session, user_id=uid) is True


@pytest.mark.asyncio
async def test_is_any_workspace_member_false_without_membership() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="x@example.com",
            password_hash="x",
            nickname="X",
            is_super_admin=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    assert await is_any_workspace_member(session, user_id=uid) is False
