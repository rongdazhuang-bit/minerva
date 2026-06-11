"""Tests for disabled user login blocking."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.domain.identity.models import User
from app.core.domain.identity.services import authenticate_user


@pytest.mark.asyncio
async def test_authenticate_user_rejects_disabled_status(monkeypatch) -> None:
    """Disabled users cannot authenticate."""

    user = User(
        id=uuid.uuid4(),
        email="disabled@example.com",
        password_hash="hashed",
        nickname="Disabled",
        status=False,
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=user))
    )
    monkeypatch.setattr(
        "app.core.domain.identity.services.verify_password",
        lambda plain, hashed: True,
    )
    result = await authenticate_user(
        session, email="disabled@example.com", password="password1"
    )
    assert result is None
