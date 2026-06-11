"""Integration tests for workspace-scoped /users routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api.deps import (
    get_current_user,
    require_workspace_member,
)
from app.sys.user.api.deps import (
    require_create_workspace_scope,
    require_workspace_manager_or_super_admin,
)
from app.core.domain.identity.models import User
from app.errors import register_exception_handlers
from app.sys.user.api.router import router as users_router

WS_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c1")


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


async def _fake_current_user() -> User:
    """Return a stub authenticated user."""

    return User(
        id=uuid.uuid4(),
        email="actor@example.com",
        password_hash="x",
        nickname="Actor",
    )


def _make_user_app(*, member: bool, admin: bool) -> FastAPI:
    """Build test app with auth dependency overrides."""

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router)
    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[require_workspace_member] = (
        _allow_member if member else _deny_member
    )
    app.dependency_overrides[require_workspace_manager_or_super_admin] = (
        _allow_admin if admin else _deny_admin
    )
    app.dependency_overrides[require_create_workspace_scope] = (
        _allow_admin if admin else _deny_admin
    )
    return app


@pytest.fixture
def member_users_client() -> Iterator[TestClient]:
    """Client with workspace member read access only."""

    yield TestClient(_make_user_app(member=True, admin=False))


@pytest.fixture
def admin_users_client() -> Iterator[TestClient]:
    """Client with workspace member + owner/admin write access."""

    yield TestClient(_make_user_app(member=True, admin=True))


def test_list_forbidden_for_non_member() -> None:
    """Non-members cannot list users."""

    client = TestClient(_make_user_app(member=False, admin=False))
    response = client.get(f"/workspaces/{WS_ID}/users")
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


def test_create_forbidden_for_member_only(member_users_client: TestClient) -> None:
    """Workspace members without owner/admin cannot create users."""

    response = member_users_client.post(
        f"/workspaces/{WS_ID}/users",
        json={
            "email": "new@example.com",
            "password": "password1",
            "nickname": "New",
            "membership_role": "member",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


def test_member_list_ok(member_users_client: TestClient, monkeypatch) -> None:
    """Members can list users."""

    async def _fake_list(*args, **kwargs):
        return [], 0

    monkeypatch.setattr(
        "app.sys.user.api.router.svc.list_users_page",
        _fake_list,
    )
    async def _fake_super(*_a, **_k):
        return False

    monkeypatch.setattr(
        "app.sys.user.api.router.is_super_admin_user",
        _fake_super,
    )
    response = member_users_client.get(f"/workspaces/{WS_ID}/users")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_capabilities_ok_for_member(member_users_client: TestClient, monkeypatch) -> None:
    """Members can read capabilities meta."""

    async def _fake_caps(*_a, **_k):
        return {
            "is_super_admin": False,
            "actor_workspace_role": "member",
            "can_edit_membership_role": False,
            "assignable_membership_roles": [],
            "can_pick_tenant_workspace": False,
            "default_tenant_id": None,
        }

    monkeypatch.setattr(
        "app.sys.user.api.router.svc.get_actor_capabilities",
        _fake_caps,
    )
    response = member_users_client.get(
        f"/workspaces/{WS_ID}/users/meta/capabilities"
    )
    assert response.status_code == 200
    assert response.json()["can_edit_membership_role"] is False


def test_tenant_meta_forbidden_for_non_super(
    member_users_client: TestClient, monkeypatch
) -> None:
    """Non-super-admin cannot list tenant meta for user form."""

    async def _fake_list(*_a, **_k):
        from app.exceptions import AppError

        raise AppError("auth.forbidden", "Super admin required", 403)

    monkeypatch.setattr(
        "app.sys.user.api.router.svc.list_tenant_meta_for_user_form",
        _fake_list,
    )
    response = member_users_client.get(f"/workspaces/{WS_ID}/users/meta/tenants")
    assert response.status_code == 403


def test_tenant_meta_ok(admin_users_client: TestClient, monkeypatch) -> None:
    """Super admin tenant meta returns sys_tenant options."""

    tid = uuid.uuid4()

    async def _fake_list(*_a, **_k):
        return [{"id": tid, "name": "Acme", "slug": "acme"}]

    monkeypatch.setattr(
        "app.sys.user.api.router.svc.list_tenant_meta_for_user_form",
        _fake_list,
    )
    response = admin_users_client.get(f"/workspaces/{WS_ID}/users/meta/tenants")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Acme"
