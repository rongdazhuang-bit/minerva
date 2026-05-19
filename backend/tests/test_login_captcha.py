"""Login CAPTCHA issue and verification."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core.infrastructure.security import login_captcha as captcha_mod
from app.exceptions import AppError
from app.main import app


@pytest.mark.asyncio
async def test_create_and_verify_login_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stored code is consumed on successful verify and rejected on reuse."""

    store: dict[str, str] = {}

    class _FakeRedis:
        def setex(self, key: str, _ttl: int, value: str) -> None:
            store[key] = value

        def get(self, key: str) -> str | None:
            return store.get(key)

        def delete(self, key: str) -> None:
            store.pop(key, None)

    monkeypatch.setattr(captcha_mod, "_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(settings, "auth_login_captcha_length", 4)

    captcha_id, image = captcha_mod.create_login_captcha()
    assert captcha_id
    assert image.startswith("data:image/svg+xml;base64,")
    key = f"minerva:auth:captcha:login:{captcha_id}"
    code = store[key]

    captcha_mod.verify_login_captcha(captcha_id, code)
    assert key not in store

    with pytest.raises(AppError) as exc:
        captcha_mod.verify_login_captcha(captcha_id, code)
    assert exc.value.code == "auth.captcha_invalid"


@pytest.mark.asyncio
async def test_login_requires_captcha_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /auth/login returns 400 when captcha fields are missing."""

    monkeypatch.setattr(settings, "auth_login_captcha_enabled", True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "secret1234",
                "captcha_id": "",
                "captcha_code": "",
            },
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_register_requires_captcha_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /auth/register returns 400 when captcha fields are missing."""

    monkeypatch.setattr(settings, "auth_login_captcha_enabled", True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "secret1234",
                "captcha_id": "",
                "captcha_code": "",
            },
        )
    assert res.status_code == 400
