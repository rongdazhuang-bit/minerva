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
async def test_dicts_and_items_crud_isolation() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        user1_email = f"du1-{uuid.uuid4().hex}@example.com"
        user2_email = f"du2-{uuid.uuid4().hex}@example.com"
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

        list_empty = await ac.get(f"/workspaces/{workspace1}/dicts", headers=h1)
        assert list_empty.status_code == 200
        assert list_empty.json() == {"items": [], "total": 0}

        create = await ac.post(
            f"/workspaces/{workspace1}/dicts",
            headers=h1,
            json={"dict_code": "gender", "dict_name": "Gender", "dict_sort": 10},
        )
        assert create.status_code == 201, create.text
        dict_id = create.json()["id"]

        dup = await ac.post(
            f"/workspaces/{workspace1}/dicts",
            headers=h1,
            json={"dict_code": "gender", "dict_name": "Dup", "dict_sort": 1},
        )
        assert dup.status_code == 409

        workspace2 = _workspace_id_from_access_token(token2)
        w2_code = f"w2-{uuid.uuid4().hex[:8]}"
        w2_ok = await ac.post(
            f"/workspaces/{workspace2}/dicts",
            headers=h2,
            json={"dict_code": w2_code, "dict_name": "W2 dict", "dict_sort": 1},
        )
        assert w2_ok.status_code == 201, w2_ok.text
        w2_dict_id = w2_ok.json()["id"]

        list_w2 = await ac.get(f"/workspaces/{workspace2}/dicts", headers=h2)
        assert list_w2.status_code == 200
        w2_body = list_w2.json()
        assert any(d["id"] == w2_dict_id for d in w2_body["items"])
        list_w1_again = await ac.get(f"/workspaces/{workspace1}/dicts", headers=h1)
        w1_items = list_w1_again.json()["items"]
        assert all(d["id"] != w2_dict_id for d in w1_items)

        other_same_code = await ac.post(
            f"/workspaces/{workspace1}/dicts",
            headers=h1,
            json={"dict_code": "status", "dict_name": "Status", "dict_sort": 5},
        )
        assert other_same_code.status_code == 201, other_same_code.text

        forbidden = await ac.get(f"/workspaces/{workspace1}/dicts", headers=h2)
        assert forbidden.status_code == 403

        list_two = await ac.get(f"/workspaces/{workspace1}/dicts", headers=h1)
        assert list_two.status_code == 200
        two_body = list_two.json()
        assert len(two_body["items"]) == 2
        assert two_body["total"] == 2

        fake_id = str(uuid.uuid4())
        not_found = await ac.patch(
            f"/workspaces/{workspace1}/dicts/{fake_id}",
            headers=h1,
            json={"dict_name": "x"},
        )
        assert not_found.status_code == 404

        items_empty = await ac.get(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items",
            headers=h1,
        )
        assert items_empty.status_code == 200
        assert items_empty.json() == []

        it1 = await ac.post(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items",
            headers=h1,
            json={"code": "m", "name": "Male", "item_sort": 2},
        )
        assert it1.status_code == 201, it1.text
        item1_id = it1.json()["id"]

        it_child = await ac.post(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items",
            headers=h1,
            json={
                "code": "m-sub",
                "name": "Sub",
                "item_sort": 1,
                "parent_uuid": item1_id,
            },
        )
        assert it_child.status_code == 201, it_child.text
        child_id = it_child.json()["id"]

        dup_item = await ac.post(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items",
            headers=h1,
            json={"code": "m", "name": "Dup code", "item_sort": 0},
        )
        assert dup_item.status_code == 409

        del_parent = await ac.delete(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items/{item1_id}",
            headers=h1,
        )
        assert del_parent.status_code == 409

        del_child = await ac.delete(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items/{child_id}",
            headers=h1,
        )
        assert del_child.status_code == 204

        del_parent_ok = await ac.delete(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items/{item1_id}",
            headers=h1,
        )
        assert del_parent_ok.status_code == 204

        cycle_root = await ac.post(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items",
            headers=h1,
            json={"code": "a", "name": "A", "item_sort": 0},
        )
        assert cycle_root.status_code == 201
        id_a = cycle_root.json()["id"]
        cycle_b = await ac.post(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items",
            headers=h1,
            json={"code": "b", "name": "B", "item_sort": 0, "parent_uuid": id_a},
        )
        assert cycle_b.status_code == 201
        id_b = cycle_b.json()["id"]

        cycle_patch = await ac.patch(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items/{id_a}",
            headers=h1,
            json={"parent_uuid": id_b},
        )
        assert cycle_patch.status_code == 400
        assert cycle_patch.json()["code"] == "dict.item_parent_cycle"

        delete_dict = await ac.delete(
            f"/workspaces/{workspace1}/dicts/{dict_id}",
            headers=h1,
        )
        assert delete_dict.status_code == 204

        gone_items = await ac.get(
            f"/workspaces/{workspace1}/dicts/{dict_id}/items",
            headers=h1,
        )
        assert gone_items.status_code == 404


@pytest.mark.asyncio
async def test_dicts_list_pagination() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        email = f"dp-{uuid.uuid4().hex}@example.com"
        password = "secret1234"
        reg = await ac.post("/auth/register", json={"email": email, "password": password})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        h = {"Authorization": f"Bearer {token}"}

        for i in range(3):
            c = await ac.post(
                f"/workspaces/{workspace_id}/dicts",
                headers=h,
                json={"dict_code": f"p{i}", "dict_name": f"P{i}", "dict_sort": i},
            )
            assert c.status_code == 201, c.text

        p1 = await ac.get(
            f"/workspaces/{workspace_id}/dicts?page=1&page_size=2",
            headers=h,
        )
        assert p1.status_code == 200
        b1 = p1.json()
        assert b1["total"] == 3
        assert len(b1["items"]) == 2

        p2 = await ac.get(
            f"/workspaces/{workspace_id}/dicts?page=2&page_size=2",
            headers=h,
        )
        assert p2.status_code == 200
        b2 = p2.json()
        assert b2["total"] == 3
        assert len(b2["items"]) == 1

        ids_p1 = {x["id"] for x in b1["items"]}
        ids_p2 = {x["id"] for x in b2["items"]}
        assert not ids_p1.intersection(ids_p2)


@pytest.mark.asyncio
async def test_dicts_list_by_code_with_item_tree() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        email = f"dc-{uuid.uuid4().hex}@example.com"
        password = "secret1234"
        reg = await ac.post("/auth/register", json={"email": email, "password": password})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        h = {"Authorization": f"Bearer {token}"}

        miss = await ac.get(
            f"/workspaces/{workspace_id}/dicts?code=nope&page=1&page_size=10",
            headers=h,
        )
        assert miss.status_code == 200
        assert miss.json() == {"items": [], "total": 0}

        create = await ac.post(
            f"/workspaces/{workspace_id}/dicts",
            headers=h,
            json={"dict_code": "KINDS", "dict_name": "Kinds", "dict_sort": 1},
        )
        assert create.status_code == 201, create.text
        dict_id = create.json()["id"]

        r1 = await ac.post(
            f"/workspaces/{workspace_id}/dicts/{dict_id}/items",
            headers=h,
            json={"code": "a", "name": "A", "item_sort": 2},
        )
        assert r1.status_code == 201, r1.text
        id_a = r1.json()["id"]
        r2 = await ac.post(
            f"/workspaces/{workspace_id}/dicts/{dict_id}/items",
            headers=h,
            json={"code": "a1", "name": "A1", "item_sort": 1, "parent_uuid": id_a},
        )
        assert r2.status_code == 201, r2.text

        by_code = await ac.get(
            f"/workspaces/{workspace_id}/dicts?code=KINDS&page=1&page_size=10",
            headers=h,
        )
        assert by_code.status_code == 200
        body = by_code.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        row0 = body["items"][0]
        assert row0["dict_code"] == "KINDS"
        assert "item_tree" in row0
        tree = row0["item_tree"]
        assert len(tree) == 1
        assert tree[0]["code"] == "a"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["code"] == "a1"

        page2 = await ac.get(
            f"/workspaces/{workspace_id}/dicts?code=KINDS&page=2&page_size=10",
            headers=h,
        )
        assert page2.status_code == 200
        b2 = page2.json()
        assert b2["total"] == 1
        assert b2["items"] == []

        no_list = await ac.get(
            f"/workspaces/{workspace_id}/dicts",
            headers=h,
        )
        assert no_list.status_code == 200
        for it in no_list.json()["items"]:
            assert "item_tree" not in it
