import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


def _decode_access_workspace_id(token: str) -> uuid.UUID:
    p = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return uuid.UUID(str(p["wid"]))


@pytest.mark.asyncio
async def test_create_rule_draft() -> None:
    email = f"r{uuid.uuid4().hex}@example.com"
    password = "secret1234"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        reg = await ac.post(
            "/auth/register", json={"email": email, "password": password}
        )
        assert reg.status_code == 201, reg.text
        tok = reg.json()
        wid = _decode_access_workspace_id(tok["access_token"])
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        r = await ac.post(
            f"/workspaces/{wid}/rules",
            headers=h,
            json={"name": "R1", "type": "document_review", "flow_json": {}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "R1"
        assert body["type"] == "document_review"
        assert str(body["workspace_id"]) == str(wid)


@pytest.mark.asyncio
async def test_publish_fails_missing_end() -> None:
    email = f"p{uuid.uuid4().hex}@example.com"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        reg = await ac.post(
            "/auth/register",
            json={"email": email, "password": "secret1234"},
        )
        assert reg.status_code == 201
        tok = reg.json()
        wid = _decode_access_workspace_id(tok["access_token"])
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        cr = await ac.post(
            f"/workspaces/{wid}/rules",
            headers=h,
            json={"name": "P1", "type": "document_review", "flow_json": {}},
        )
        assert cr.status_code == 201, cr.text
        rule_id = cr.json()["id"]
        bad = {
            "schema_version": 1,
            "nodes": [{"id": "1", "type": "start", "data": {}}],
            "edges": [],
        }
        v2 = await ac.post(
            f"/workspaces/{wid}/rules/{rule_id}/versions",
            headers=h,
            json={"flow_json": bad},
        )
        assert v2.status_code == 201, v2.text
        vid = v2.json()["id"]
        pub = await ac.post(
            f"/workspaces/{wid}/rules/{rule_id}/versions/{vid}/publish",
            headers=h,
        )
        assert pub.status_code == 400, pub.text
        assert pub.json()["code"] == "flow.missing_end"


@pytest.mark.asyncio
async def test_add_version_and_publish() -> None:
    email = f"q{uuid.uuid4().hex}@example.com"
    flow_ok = {
        "schema_version": 1,
        "nodes": [
            {"id": "a", "type": "start", "data": {}},
            {"id": "b", "type": "end", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "a", "target": "b"}],
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        reg = await ac.post(
            "/auth/register",
            json={"email": email, "password": "secret1234"},
        )
        assert reg.status_code == 201
        tok = reg.json()
        wid = _decode_access_workspace_id(tok["access_token"])
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        cr = await ac.post(
            f"/workspaces/{wid}/rules",
            headers=h,
            json={"name": "P2", "type": "document_review", "flow_json": {}},
        )
        assert cr.status_code == 201
        rule_id = cr.json()["id"]
        v2 = await ac.post(
            f"/workspaces/{wid}/rules/{rule_id}/versions",
            headers=h,
            json={"flow_json": flow_ok},
        )
        assert v2.status_code == 201, v2.text
        assert v2.json()["version"] == 2
        vid = v2.json()["id"]
        pub = await ac.post(
            f"/workspaces/{wid}/rules/{rule_id}/versions/{vid}/publish",
            headers=h,
        )
        assert pub.status_code == 200, pub.text
        assert pub.json()["state"] == "published"
