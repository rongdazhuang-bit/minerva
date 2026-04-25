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


@pytest.mark.asyncio
async def test_model_providers_crud_and_isolation() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        user1_email = f"mp-u1-{uuid.uuid4().hex}@example.com"
        user2_email = f"mp-u2-{uuid.uuid4().hex}@example.com"
        password = "secret1234"

        reg1 = await ac.post("/auth/register", json={"email": user1_email, "password": password})
        assert reg1.status_code == 201, reg1.text
        token1 = reg1.json()["access_token"]
        workspace1 = _workspace_id_from_access_token(token1)

        reg2 = await ac.post("/auth/register", json={"email": user2_email, "password": password})
        assert reg2.status_code == 201, reg2.text
        token2 = reg2.json()["access_token"]

        h1 = {"Authorization": f"Bearer {token1}"}
        h2 = {"Authorization": f"Bearer {token2}"}

        list_empty = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models", headers=h1
        )
        assert list_empty.status_code == 200
        assert list_empty.json() == []

        create = await ac.post(
            f"/workspaces/{workspace1}/model-providers/models",
            headers=h1,
            json={
                "provider_name": "ACME",
                "model_name": "gpt-4o",
                "model_type": "chat",
                "auth_type": "API_KEY",
                "api_key": "secret-key",
            },
        )
        assert create.status_code == 201, create.text
        body = create.json()
        model_id = body["id"]
        assert body["api_key"] == "secret-key"

        list_one = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models", headers=h1
        )
        assert list_one.status_code == 200
        rows = list_one.json()
        assert len(rows) == 1
        assert rows[0]["id"] == model_id
        assert rows[0].get("api_key") is None
        assert rows[0].get("auth_passwd") is None
        assert rows[0]["has_api_key"] is True
        assert rows[0]["has_password"] is False

        grouped = await ac.get(
            f"/workspaces/{workspace1}/model-providers/grouped", headers=h1
        )
        assert grouped.status_code == 200, grouped.text
        groups = grouped.json()
        assert len(groups) == 1
        assert groups[0]["provider_name"] == "ACME"
        assert len(groups[0]["items"]) == 1
        assert groups[0]["items"][0]["id"] == model_id

        forbidden = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models", headers=h2
        )
        assert forbidden.status_code == 403

        detail = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models/{model_id}", headers=h1
        )
        assert detail.status_code == 200
        assert detail.json()["api_key"] == "secret-key"

        fake_id = str(uuid.uuid4())
        not_found = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models/{fake_id}", headers=h1
        )
        assert not_found.status_code == 404

        patch = await ac.patch(
            f"/workspaces/{workspace1}/model-providers/models/{model_id}",
            headers=h1,
            json={"model_name": "gpt-4o-mini", "api_key": None},
        )
        assert patch.status_code == 200, patch.text
        assert patch.json()["model_name"] == "gpt-4o-mini"
        assert patch.json()["api_key"] is None

        list_after_patch = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models", headers=h1
        )
        assert list_after_patch.status_code == 200
        assert list_after_patch.json()[0]["has_api_key"] is False

        delete = await ac.delete(
            f"/workspaces/{workspace1}/model-providers/models/{model_id}", headers=h1
        )
        assert delete.status_code == 204

        gone = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models/{model_id}", headers=h1
        )
        assert gone.status_code == 404
