"""Tests for tenant owner/admin gate used by menu management."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.domain.identity.models import MembershipRole
from app.core.domain.identity.models import User
from app.core.domain.identity.services import (
    is_any_tenant_owner_or_admin,
    is_super_admin_user,
)


@pytest.mark.asyncio
async def test_is_any_tenant_owner_or_admin_true_for_admin() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="admin@example.com",
            password_hash="x",
            nickname="Admin",
            is_super_admin=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    session.execute = AsyncMock(return_value=result)

    ok = await is_any_tenant_owner_or_admin(session, user_id=uid)
    assert ok is True


@pytest.mark.asyncio
async def test_is_any_tenant_owner_or_admin_false_for_member_only() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="member@example.com",
            password_hash="x",
            nickname="Member",
            is_super_admin=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    ok = await is_any_tenant_owner_or_admin(session, user_id=uid)
    assert ok is False


def test_membership_role_includes_owner_and_admin() -> None:
    assert MembershipRole.owner in (MembershipRole.owner, MembershipRole.admin)
    assert MembershipRole.member not in (MembershipRole.owner, MembershipRole.admin)


@pytest.mark.asyncio
async def test_is_super_admin_user_true() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="rongda@yeah.net",
            password_hash="x",
            nickname="Rongda",
            is_super_admin=True,
        )
    )
    assert await is_super_admin_user(session, user_id=uid) is True


@pytest.mark.asyncio
async def test_is_any_tenant_owner_or_admin_true_for_super_admin() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="rongda@yeah.net",
            password_hash="x",
            nickname="Rongda",
            is_super_admin=True,
        )
    )
    session.execute = AsyncMock()
    assert await is_any_tenant_owner_or_admin(session, user_id=uid) is True
