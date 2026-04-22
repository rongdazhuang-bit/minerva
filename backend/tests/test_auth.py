import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_register_login_refresh() -> None:
    email = f"u{uuid.uuid4().hex}@example.com"
    password = "secret1234"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        reg = await ac.post(
            "/auth/register", json={"email": email, "password": password}
        )
        assert reg.status_code == 201, reg.text
        tok1 = reg.json()
        assert tok1["token_type"] == "bearer"
        assert "access_token" in tok1 and "refresh_token" in tok1

        bad = await ac.post(
            "/auth/login", json={"email": email, "password": "wrong"}
        )
        assert bad.status_code == 401

        log = await ac.post(
            "/auth/login", json={"email": email, "password": password}
        )
        assert log.status_code == 200
        tok2 = log.json()

        ref = await ac.post(
            "/auth/refresh",
            json={"refresh_token": tok2["refresh_token"]},
        )
        assert ref.status_code == 200
        tok3 = ref.json()
        assert tok3["refresh_token"] != tok2["refresh_token"]

        old_ref = await ac.post(
            "/auth/refresh",
            json={"refresh_token": tok2["refresh_token"]},
        )
        assert old_ref.status_code == 401
