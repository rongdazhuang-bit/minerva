from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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

        mid = uuid.uuid4()
        cfg = MagicMock()
        cfg.model_id = mid
        cfg.sys_prompt = "你是校审助手"
        cfg.user_prompt = "请润色以下规则"
        cfg.chat_memory = None
        model = MagicMock()
        model.model_name = "test-model"
        model.endpoint_url = "http://127.0.0.1:9/v1"
        model.api_key = "sk-test"
        model.auth_type = "API_KEY"
        model.enabled = True
        model.max_tokens_to_sample = None
        completion = {
            "choices": [{"message": {"content": "  polished line  "}}],
        }
        with (
            patch(
                "app.rule.service.rule_base_service.rcp_repo.try_resolve",
                new_callable=AsyncMock,
                return_value=cfg,
            ),
            patch(
                "app.rule.service.rule_base_service.model_svc.get_model",
                new_callable=AsyncMock,
                return_value=model,
            ),
            patch(
                "app.rule.service.rule_base_service.chat_service.complete",
                new_callable=AsyncMock,
                return_value=completion,
            ),
        ):
            polish = await ac.post(
                f"/workspaces/{workspace1}/rule-base/polish-review-rules",
                headers=h1,
                json={"review_rules": "  raw  "},
            )
        assert polish.status_code == 200, polish.text
        assert polish.json()["review_rules_ai"] == "polished line"

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

        patch_serial = await ac.patch(
            f"/workspaces/{workspace1}/rule-base/{rule_id}",
            headers=h1,
            json={"serial_number": "R-002"},
        )
        assert patch_serial.status_code == 200, patch_serial.text
        assert patch_serial.json()["serial_number"] == "R-002"

        forbidden = await ac.get(f"/workspaces/{workspace1}/rule-base", headers=h2)
        assert forbidden.status_code == 403

        remove = await ac.delete(
            f"/workspaces/{workspace1}/rule-base/{rule_id}",
            headers=h1,
        )
        assert remove.status_code == 204

        list_after = await ac.get(f"/workspaces/{workspace1}/rule-base", headers=h1)
        assert list_after.json()["total"] == 0


@pytest.mark.asyncio
async def test_rule_base_overview_stats() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        user1_email = f"rbos-{uuid.uuid4().hex}@example.com"
        user2_email = f"rbos2-{uuid.uuid4().hex}@example.com"
        password = "secret1234"

        reg1 = await ac.post("/auth/register", json={"email": user1_email, "password": password})
        assert reg1.status_code == 201, reg1.text
        token1 = reg1.json()["access_token"]
        workspace1 = _workspace_id_from_access_token(token1)
        h1 = {"Authorization": f"Bearer {token1}"}

        reg2 = await ac.post("/auth/register", json={"email": user2_email, "password": password})
        assert reg2.status_code == 201, reg2.text
        token2 = reg2.json()["access_token"]
        h2 = {"Authorization": f"Bearer {token2}"}

        clear = await ac.get(
            f"/workspaces/{workspace1}/rule-base/overview-stats", headers=h1
        )
        assert clear.status_code == 200, clear.text
        assert clear.json() == {
            "rule_count": 0,
            "engineering_codes": [],
            "subject_codes": [],
            "document_type_codes": [],
        }

        def _body(**kw: object) -> dict:
            b = {
                "sequence_number": 1,
                "engineering_code": None,
                "subject_code": None,
                "serial_number": "R",
                "document_type": None,
                "review_section": "sec",
                "review_object": "obj",
                "review_rules": "rule",
                "review_result": "res",
                "status": "Y",
            }
            b.update(kw)
            return b

        for spec in (
            {
                "sequence_number": 1,
                "engineering_code": "E1",
                "subject_code": "S1",
                "document_type": "D1",
            },
            {
                "sequence_number": 2,
                "engineering_code": "E1",
                "subject_code": "S1",
                "document_type": "D1",
            },
            {
                "sequence_number": 3,
                "engineering_code": "E2",
                "subject_code": None,
                "document_type": None,
            },
        ):
            cr = await ac.post(
                f"/workspaces/{workspace1}/rule-base",
                headers=h1,
                json=_body(**spec),
            )
            assert cr.status_code == 201, cr.text

        r = await ac.get(
            f"/workspaces/{workspace1}/rule-base/overview-stats", headers=h1
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["rule_count"] == 3
        assert data["engineering_codes"] == ["E1", "E2"]
        assert data["subject_codes"] == ["S1"]
        assert data["document_type_codes"] == ["D1"]

        forbidden = await ac.get(
            f"/workspaces/{workspace1}/rule-base/overview-stats", headers=h2
        )
        assert forbidden.status_code == 403
