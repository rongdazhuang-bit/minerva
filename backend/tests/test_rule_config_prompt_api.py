from __future__ import annotations

import os
import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core.infrastructure.db.session import async_session_factory
from app.main import app
from app.rule.service.rule_config_prompt_service import resolve_rule_config_prompt
from app.sys.model_provider.domain.db.models import SysModel


def _should_skip_db_tests() -> bool:
    if os.environ.get("MINERVA_SKIP_DB_TESTS", "").lower() in ("1", "true", "yes"):
        return True
    return False


pytestmark = pytest.mark.skipif(
    _should_skip_db_tests(),
    reason="Set MINERVA_SKIP_DB_TESTS=1 to skip",
)


def _workspace_id_from_access_token(access_token: str) -> str:
    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


async def _seed_sys_model(workspace_id: uuid.UUID) -> uuid.UUID:
    mid = uuid.uuid4()
    async with async_session_factory() as session:
        row = SysModel(
            id=mid,
            workspace_id=workspace_id,
            provider_name="P",
            model_name="M",
            model_type="T",
            enabled=True,
            load_balancing_enabled=False,
            auth_type="NONE",
        )
        session.add(row)
        await session.commit()
    return mid


@pytest.mark.asyncio
async def test_rule_config_prompt_crud_and_conflict() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        email = f"rcp-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        ws = uuid.UUID(_workspace_id_from_access_token(token))
        headers = {"Authorization": f"Bearer {token}"}

        model_id = await _seed_sys_model(ws)

        empty = await ac.get(
            f"/workspaces/{ws}/rule-config/config-prompts",
            headers=headers,
        )
        assert empty.status_code == 200
        assert empty.json() == {"items": [], "total": 0}

        body = {
            "model_id": str(model_id),
            "engineering_code": "E1",
            "subject_code": None,
            "document_type": None,
            "sys_prompt": "hello",
        }
        c1 = await ac.post(
            f"/workspaces/{ws}/rule-config/config-prompts",
            headers=headers,
            json=body,
        )
        assert c1.status_code == 201, c1.text
        cpid = c1.json()["id"]
        assert c1.json()["provider_name"] == "P"
        assert c1.json()["model_name"] == "M"

        dup = await ac.post(
            f"/workspaces/{ws}/rule-config/config-prompts",
            headers=headers,
            json=body,
        )
        assert dup.status_code == 409

        one = await ac.get(
            f"/workspaces/{ws}/rule-config/config-prompts/{cpid}",
            headers=headers,
        )
        assert one.status_code == 200
        assert one.json()["sys_prompt"] == "hello"

        patch = await ac.patch(
            f"/workspaces/{ws}/rule-config/config-prompts/{cpid}",
            headers=headers,
            json={"sys_prompt": "bye"},
        )
        assert patch.status_code == 200
        assert patch.json()["sys_prompt"] == "bye"

        rm = await ac.delete(
            f"/workspaces/{ws}/rule-config/config-prompts/{cpid}",
            headers=headers,
        )
        assert rm.status_code == 204


@pytest.mark.asyncio
async def test_resolve_rule_config_prompt_fallback_order() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        email = f"rcp2-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        ws = uuid.UUID(_workspace_id_from_access_token(token))
        headers = {"Authorization": f"Bearer {token}"}
        model_id = await _seed_sys_model(ws)

        async def post_cfg(payload: dict) -> None:
            r = await ac.post(
                f"/workspaces/{ws}/rule-config/config-prompts",
                headers=headers,
                json={"model_id": str(model_id), **payload},
            )
            assert r.status_code == 201, r.text

        await post_cfg({"sys_prompt": "global"})
        await post_cfg({"engineering_code": "E", "sys_prompt": "e"})
        await post_cfg({"engineering_code": "E", "subject_code": "S", "sys_prompt": "es"})
        await post_cfg(
            {
                "engineering_code": "E",
                "subject_code": "S",
                "document_type": "D",
                "sys_prompt": "esd",
            }
        )

    async with async_session_factory() as session:
        r = await resolve_rule_config_prompt(
            session,
            workspace_id=ws,
            engineering_code="E",
            subject_code="S",
            document_type="D",
        )
        assert r.sys_prompt == "esd"

        r2 = await resolve_rule_config_prompt(
            session,
            workspace_id=ws,
            engineering_code="E",
            subject_code="S",
            document_type="other",
        )
        assert r2.sys_prompt == "es"

        r3 = await resolve_rule_config_prompt(
            session,
            workspace_id=ws,
            engineering_code="E",
            subject_code=None,
            document_type=None,
        )
        assert r3.sys_prompt == "e"

        r4 = await resolve_rule_config_prompt(
            session,
            workspace_id=ws,
            engineering_code=None,
            subject_code=None,
            document_type=None,
        )
        assert r4.sys_prompt == "global"

        r5 = await resolve_rule_config_prompt(
            session,
            workspace_id=ws,
            engineering_code="NOPE",
            subject_code=None,
            document_type=None,
        )
        assert r5.sys_prompt == "global"


@pytest.mark.asyncio
async def test_resolve_rule_config_prompt_raises_when_empty() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        email = f"rcp3-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        ws = uuid.UUID(_workspace_id_from_access_token(token))
        await _seed_sys_model(ws)

    from app.exceptions import AppError

    async with async_session_factory() as session:
        with pytest.raises(AppError) as ei:
            await resolve_rule_config_prompt(
                session,
                workspace_id=ws,
                engineering_code="X",
                subject_code=None,
                document_type=None,
            )
        assert ei.value.code == "rule_config_prompt.not_found"
