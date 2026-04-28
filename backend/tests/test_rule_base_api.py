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


def _sample_rule_json() -> dict:
    return {
        "sequence_number": 1,
        "subject_code": None,
        "serial_number": "R-001",
        "document_type": None,
        "review_section": "sec",
        "review_object": "obj",
        "review_rules": "rule text",
        "review_result": "result text",
        "status": "Y",
    }


@pytest.mark.asyncio
async def test_rule_base_crud_and_isolation() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        user1_email = f"rb1-{uuid.uuid4().hex}@example.com"
        user2_email = f"rb2-{uuid.uuid4().hex}@example.com"
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

        list_empty = await ac.get(f"/workspaces/{workspace1}/rule-base", headers=h1)
        assert list_empty.status_code == 200
        assert list_empty.json() == {"items": [], "total": 0}

        create = await ac.post(
            f"/workspaces/{workspace1}/rule-base",
            headers=h1,
            json=_sample_rule_json(),
        )
        assert create.status_code == 201, create.text
        rule_id = create.json()["id"]
        assert create.json()["review_section"] == "sec"
        assert create.json().get("review_rules_ai") is None

        polish = await ac.post(
            f"/workspaces/{workspace1}/rule-base/polish-review-rules",
            headers=h1,
            json={"review_rules": "  raw  "},
        )
        assert polish.status_code == 200, polish.text
        assert polish.json()["review_rules_ai"].endswith("raw")

        patch_ai = await ac.patch(
            f"/workspaces/{workspace1}/rule-base/{rule_id}",
            headers=h1,
            json={"review_rules_ai": " ai line "},
        )
        assert patch_ai.status_code == 200, patch_ai.text
        assert patch_ai.json()["review_rules_ai"] == "ai line"

        list_one = await ac.get(f"/workspaces/{workspace1}/rule-base", headers=h1)
        assert list_one.status_code == 200
        body = list_one.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

        fake_id = str(uuid.uuid4())
        not_found = await ac.patch(
            f"/workspaces/{workspace1}/rule-base/{fake_id}",
            headers=h1,
            json={"serial_number": "x"},
        )
        assert not_found.status_code == 404

        patch = await ac.patch(
            f"/workspaces/{workspace1}/rule-base/{rule_id}",
            headers=h1,
            json={"serial_number": "R-002"},
        )
        assert patch.status_code == 200, patch.text
        assert patch.json()["serial_number"] == "R-002"

        forbidden = await ac.get(f"/workspaces/{workspace1}/rule-base", headers=h2)
        assert forbidden.status_code == 403

        remove = await ac.delete(
            f"/workspaces/{workspace1}/rule-base/{rule_id}",
            headers=h1,
        )
        assert remove.status_code == 204

        list_after = await ac.get(f"/workspaces/{workspace1}/rule-base", headers=h1)
        assert list_after.json()["total"] == 0
