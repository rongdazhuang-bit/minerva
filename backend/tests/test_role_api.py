"""Integration tests for workspace-scoped /roles routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api.deps import require_workspace_member, require_workspace_owner_or_admin
from app.errors import register_exception_handlers
from app.sys.role.api.router import router as roles_router

WS_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000b1")


async def _deny_member(workspace_id: uuid.UUID) -> uuid.UUID:
    """Simulate non-member access."""

    from app.exceptions import AppError

    raise AppError("auth.forbidden", "Not a workspace member", 403)


async def _allow_member(workspace_id: uuid.UUID) -> uuid.UUID:
    """Simulate workspace member access."""

    return workspace_id


async def _deny_admin(workspace_id: uuid.UUID) -> uuid.UUID:
    """Simulate member without owner/admin role."""

    from app.exceptions import AppError

    raise AppError("auth.forbidden", "Not workspace owner/admin", 403)


async def _allow_admin(workspace_id: uuid.UUID) -> uuid.UUID:
    """Simulate workspace owner/admin access."""

    return workspace_id


def _make_role_app(*, member: bool, admin: bool) -> FastAPI:
    """Build test app with auth dependency overrides."""

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(roles_router)
    app.dependency_overrides[require_workspace_member] = (
        _allow_member if member else _deny_member
    )
    app.dependency_overrides[require_workspace_owner_or_admin] = (
        _allow_admin if admin else _deny_admin
    )
    return app


@pytest.fixture
def member_roles_client() -> Iterator[TestClient]:
    """Client with workspace member read access only."""

    yield TestClient(_make_role_app(member=True, admin=False))


@pytest.fixture
def admin_roles_client() -> Iterator[TestClient]:
    """Client with workspace member + owner/admin write access."""

    yield TestClient(_make_role_app(member=True, admin=True))


def test_list_forbidden_for_non_member() -> None:
    """Non-members cannot list roles."""

    client = TestClient(_make_role_app(member=False, admin=False))
    response = client.get(f"/workspaces/{WS_ID}/roles")
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


def test_create_forbidden_for_member_only(member_roles_client: TestClient) -> None:
    """Workspace members without owner/admin cannot create roles."""

    response = member_roles_client.post(
        f"/workspaces/{WS_ID}/roles",
        json={"role_name": "测试", "role_key": "test", "menu_ids": []},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


def test_member_list_ok(member_roles_client: TestClient, monkeypatch) -> None:
    """Members can list roles."""

    from app.sys.role.domain.db.models import SysRole

    row = SysRole(
        id=ROLE_ID,
        workspace_id=WS_ID,
        role_name="管理员",
        role_key="admin",
        role_sort=0,
        status=True,
    )

    async def fake_list_page(*_args, **_kwargs):
        return [row], 1

    monkeypatch.setattr(
        "app.sys.role.api.router.svc.list_roles_page",
        fake_list_page,
    )
    response = member_roles_client.get(f"/workspaces/{WS_ID}/roles")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["role_key"] == "admin"


def test_admin_create_ok(admin_roles_client: TestClient, monkeypatch) -> None:
    """Owner/admin can create roles."""

    from app.sys.role.domain.db.models import SysRole

    row = SysRole(
        id=ROLE_ID,
        workspace_id=WS_ID,
        role_name="管理员",
        role_key="admin",
        role_sort=0,
        status=True,
    )

    async def fake_create(*_args, **_kwargs):
        return row

    async def fake_detail(*_args, **_kwargs):
        return row, []

    monkeypatch.setattr("app.sys.role.api.router.svc.create_role", fake_create)
    monkeypatch.setattr("app.sys.role.api.router.svc.get_role_detail", fake_detail)

    response = admin_roles_client.post(
        f"/workspaces/{WS_ID}/roles",
        json={"role_name": "管理员", "role_key": "admin", "menu_ids": []},
    )
    assert response.status_code == 201
    assert response.json()["role_key"] == "admin"


def test_get_role_not_found(admin_roles_client: TestClient, monkeypatch) -> None:
    """Missing role returns 404."""

    from app.exceptions import AppError

    async def fake_detail(*_args, **_kwargs):
        raise AppError("role.not_found", "Role not found", 404)

    monkeypatch.setattr("app.sys.role.api.router.svc.get_role_detail", fake_detail)
    response = admin_roles_client.get(f"/workspaces/{WS_ID}/roles/{ROLE_ID}")
    assert response.status_code == 404
    assert response.json()["code"] == "role.not_found"


def test_menu_tree_before_role_id_route(member_roles_client: TestClient, monkeypatch) -> None:
    """menu-tree route is registered and reachable."""

    async def fake_tree(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.sys.role.api.router.svc.list_menu_tree_for_role_assignment",
        fake_tree,
    )
    response = member_roles_client.get(f"/workspaces/{WS_ID}/roles/menu-tree")
    assert response.status_code == 200
    assert response.json() == []
