"""Integration tests for /sys/menus routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.errors import register_exception_handlers
from app.sys.menu.api.deps import require_any_tenant_owner_or_admin
from app.sys.menu.api.router import router as menus_router

TEST_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000099")


def _fake_user() -> User:
    return User(
        id=TEST_USER_ID,
        email="menu-test@example.com",
        password_hash="x",
    )


async def _allow_admin() -> User:
    return _fake_user()


async def _deny_admin() -> User:
    from app.exceptions import AppError

    raise AppError("auth.forbidden", "Only tenant owner/admin can manage menus", 403)


def _make_menu_app(*, admin: bool) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(menus_router)
    app.dependency_overrides[get_current_user] = _allow_admin
    app.dependency_overrides[require_any_tenant_owner_or_admin] = (
        _allow_admin if admin else _deny_admin
    )
    return app


@pytest.fixture
def member_menu_client() -> Iterator[TestClient]:
    yield TestClient(_make_menu_app(admin=False))


@pytest.fixture
def admin_menu_client() -> Iterator[TestClient]:
    yield TestClient(_make_menu_app(admin=True))


def test_list_forbidden_for_non_admin(member_menu_client: TestClient) -> None:
    response = member_menu_client.get("/sys/menus")
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


def test_nav_requires_auth() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(menus_router)
    client = TestClient(app)
    response = client.get("/sys/menus/nav")
    assert response.status_code == 401


def test_admin_list_ok(admin_menu_client: TestClient, monkeypatch) -> None:
    """Admin list endpoint returns tree from service."""

    from app.sys.menu.api.schemas import SysMenuNodeOut

    async def fake_list_tree(*_args, **_kwargs):
        return [
            SysMenuNodeOut(
                id=uuid.uuid4(),
                parent_id=None,
                menu_name="概览",
                menu_key="overview",
                order_num=1,
                menu_type="C",
                path="/app/overview",
                visible=True,
                status=True,
                is_external=False,
            )
        ]

    monkeypatch.setattr(
        "app.sys.menu.api.router.svc.list_menu_tree",
        fake_list_tree,
    )
    response = admin_menu_client.get("/sys/menus")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["menu_name"] == "概览"


def test_admin_delete_cascade_returns_count(admin_menu_client: TestClient, monkeypatch) -> None:
    menu_id = uuid.uuid4()

    async def fake_delete_cascade(*_args, **_kwargs):
        return 3

    monkeypatch.setattr(
        "app.sys.menu.api.router.svc.delete_menu_cascade",
        fake_delete_cascade,
    )
    response = admin_menu_client.delete(f"/sys/menus/{menu_id}")
    assert response.status_code == 200
    assert response.json() == {"deleted_count": 3}
