from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


def _workspace_id_from_access_token(access_token: str) -> str:
    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


@pytest.mark.asyncio
async def test_model_providers_grouped_empty_list() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        email = f"mp-empty-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        wid = _workspace_id_from_access_token(token)
        h = {"Authorization": f"Bearer {token}"}

        resp = await ac.get(f"/workspaces/{wid}/model-providers/grouped", headers=h)
        assert resp.status_code == 200
        assert resp.json() == []
