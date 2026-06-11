"""Tests for disabled-user guards on auth dependencies."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.api.deps import get_current_user
from app.exceptions import AppError
from app.core.domain.identity.models import User


@pytest.mark.asyncio
async def test_get_current_user_rejects_disabled_status(monkeypatch) -> None:
    """Disabled users cannot pass get_current_user."""

    uid = uuid.uuid4()
    user = User(
        id=uid,
        email="disabled@example.com",
        password_hash="hashed",
        nickname="Disabled",
        status=False,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=user)

    def fake_decode(_token: str) -> dict[str, str]:
        return {"type": "access", "sub": str(uid)}

    monkeypatch.setattr(
        "app.core.api.deps.decode_token",
        fake_decode,
    )

    with pytest.raises(AppError) as exc:
        await get_current_user(
            cred=MagicMock(scheme="Bearer", credentials="token"),
            session=session,
        )
    assert exc.value.code == "user.disabled"
    assert exc.value.status_code == 401
