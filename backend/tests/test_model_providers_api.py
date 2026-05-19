from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.core.domain.identity.models import MembershipRole, User, WorkspaceMembership
from app.core.infrastructure.db.session import async_session_factory
from app.main import app


def _workspace_id_from_access_token(access_token: str) -> str:
    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


async def _list_dicts_all(ac: AsyncClient, workspace_id: str, headers: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    page = 1
    page_size = 100
    while True:
        r = await ac.get(
            f"/workspaces/{workspace_id}/dicts?page={page}&page_size={page_size}",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        items = body["items"]
        out.extend(items)
        if len(out) >= body["total"] or len(items) == 0:
            break
        page += 1
    return out


async def _get_or_create_dict_id(
    ac: AsyncClient, workspace_id: str, headers: dict[str, str], dict_code: str, dict_name: str
) -> str:
    for d in await _list_dicts_all(ac, workspace_id, headers):
        if d["dict_code"] == dict_code:
            return d["id"]
    created = await ac.post(
        f"/workspaces/{workspace_id}/dicts",
        headers=headers,
        json={"dict_code": dict_code, "dict_name": dict_name, "dict_sort": 0},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _add_dict_item(
    ac: AsyncClient, workspace_id: str, headers: dict[str, str], dict_id: str, code: str, name: str
) -> None:
    r = await ac.post(
        f"/workspaces/{workspace_id}/dicts/{dict_id}/items",
        headers=headers,
        json={"code": code, "name": name, "item_sort": 0},
    )
    assert r.status_code in (201, 409), r.text


MODEL_TYPE_DICT_CODE_CHAT = "CHAT"


async def _seed_model_provider_dicts(
    ac: AsyncClient, workspace_id: str, headers: dict[str, str]
) -> str:
    """Seed MODEL_PROVIDER / MODEL_TYPE dicts; returns provider dict item code."""
    p_id = await _get_or_create_dict_id(
        ac, workspace_id, headers, "MODEL_PROVIDER", "Model providers"
    )
    t_id = await _get_or_create_dict_id(
        ac, workspace_id, headers, "MODEL_TYPE", "Model types"
    )

    provider_code = f"p-{uuid.uuid4().hex[:8]}"
    await _add_dict_item(ac, workspace_id, headers, p_id, provider_code, "OpenAI")
    await _add_dict_item(
        ac, workspace_id, headers, t_id, MODEL_TYPE_DICT_CODE_CHAT, "chat"
    )
    return provider_code


async def _add_user_to_workspace(*, user_email: str, workspace_id: str, role: MembershipRole) -> None:
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.email == user_email))
        user = r.scalar_one()
        row = WorkspaceMembership(
            user_id=user.id,
            workspace_id=uuid.UUID(workspace_id),
            role=role,
        )
        s.add(row)
        await s.commit()


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

        provider_code = await _seed_model_provider_dicts(ac, workspace1, h1)

        list_empty = await ac.get(
            f"/workspaces/{workspace1}/model-providers/models", headers=h1
        )
        assert list_empty.status_code == 200
        assert list_empty.json() == []

        create = await ac.post(
            f"/workspaces/{workspace1}/model-providers/models",
            headers=h1,
            json={
                "provider_name": provider_code,
                "model_name": "gpt-4o",
                "model_type": MODEL_TYPE_DICT_CODE_CHAT,
                "auth_type": "API_KEY",
                "api_key": "secret-key",
            },
        )
        assert create.status_code == 201, create.text
        body = create.json()
        model_id = body["id"]
        assert body["provider_name"] == provider_code
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
        assert groups[0]["provider_name"] == provider_code
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


@pytest.mark.asyncio
async def test_model_provider_member_cannot_write() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        owner_email = f"mp-own-{uuid.uuid4().hex}@example.com"
        member_email = f"mp-mem-{uuid.uuid4().hex}@example.com"
        password = "secret1234"

        oreg = await ac.post("/auth/register", json={"email": owner_email, "password": password})
        assert oreg.status_code == 201, oreg.text
        owner_tok = oreg.json()["access_token"]
        wid = _workspace_id_from_access_token(owner_tok)
        h_owner = {"Authorization": f"Bearer {owner_tok}"}

        mreg = await ac.post("/auth/register", json={"email": member_email, "password": password})
        assert mreg.status_code == 201, mreg.text
        member_tok = mreg.json()["access_token"]
        h_member = {"Authorization": f"Bearer {member_tok}"}

        await _add_user_to_workspace(user_email=member_email, workspace_id=wid, role=MembershipRole.member)
        provider_code = await _seed_model_provider_dicts(ac, wid, h_owner)

        create_forbidden = await ac.post(
            f"/workspaces/{wid}/model-providers/models",
            headers=h_member,
            json={
                "provider_name": provider_code,
                "model_name": "x",
                "model_type": MODEL_TYPE_DICT_CODE_CHAT,
                "auth_type": "NONE",
            },
        )
        assert create_forbidden.status_code == 403

        create_ok = await ac.post(
            f"/workspaces/{wid}/model-providers/models",
            headers=h_owner,
            json={
                "provider_name": provider_code,
                "model_name": "x",
                "model_type": MODEL_TYPE_DICT_CODE_CHAT,
                "auth_type": "NONE",
            },
        )
        assert create_ok.status_code == 201, create_ok.text
        mid = create_ok.json()["id"]

        patch_forbidden = await ac.patch(
            f"/workspaces/{wid}/model-providers/models/{mid}",
            headers=h_member,
            json={"model_name": "y"},
        )
        assert patch_forbidden.status_code == 403

        delete_forbidden = await ac.delete(
            f"/workspaces/{wid}/model-providers/models/{mid}",
            headers=h_member,
        )
        assert delete_forbidden.status_code == 403

        read_ok = await ac.get(f"/workspaces/{wid}/model-providers/models", headers=h_member)
        assert read_ok.status_code == 200
        assert len(read_ok.json()) == 1


@pytest.mark.asyncio
async def test_model_provider_dict_code_validation() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        email = f"mp-dict-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        wid = _workspace_id_from_access_token(token)
        h = {"Authorization": f"Bearer {token}"}
        provider_code = await _seed_model_provider_dicts(ac, wid, h)

        bad_provider = await ac.post(
            f"/workspaces/{wid}/model-providers/models",
            headers=h,
            json={
                "provider_name": "NotARealProvider",
                "model_name": "x",
                "model_type": MODEL_TYPE_DICT_CODE_CHAT,
                "auth_type": "NONE",
            },
        )
        assert bad_provider.status_code == 422
        assert bad_provider.json()["code"] == "model_provider.provider_name_invalid"

        bad_type = await ac.post(
            f"/workspaces/{wid}/model-providers/models",
            headers=h,
            json={
                "provider_name": provider_code,
                "model_name": "x",
                "model_type": "not-a-type",
                "auth_type": "NONE",
            },
        )
        assert bad_type.status_code == 422
        assert bad_type.json()["code"] == "model_provider.model_type_invalid"
