"""Integration tests for nested /sys/tenants/{id}/workspaces routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.domain.identity.models import User, Workspace
from app.errors import register_exception_handlers
from app.exceptions import AppError
from app.sys.tenant.api.deps import require_super_admin
from app.sys.tenant.api.router import router as tenants_router

TENANT_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c1")
WORKSPACE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000d1")


async def _deny_super_admin() -> User:
    """Simulate non-super-admin access."""

    raise AppError("auth.forbidden", "Not super admin", 403)


async def _allow_super_admin() -> User:
    """Simulate super-admin access."""

    return User(
        id=uuid.uuid4(),
        email="sa@example.com",
        password_hash="x",
        is_super_admin=True,
    )


def _make_app(*, super_admin: bool) -> FastAPI:
    """Build test app with auth dependency overrides."""

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(tenants_router)
    app.dependency_overrides[require_super_admin] = (
        _allow_super_admin if super_admin else _deny_super_admin
    )
    return app


@pytest.fixture
def sa_client() -> Iterator[TestClient]:
    """Client with super-admin access."""

    yield TestClient(_make_app(super_admin=True))


@pytest.fixture
def forbidden_client() -> Iterator[TestClient]:
    """Client without super-admin access."""

    yield TestClient(_make_app(super_admin=False))


def test_list_workspaces_forbidden(forbidden_client: TestClient) -> None:
    """Non-super-admin users cannot list workspaces."""

    response = forbidden_client.get(f"/sys/tenants/{TENANT_ID}/workspaces")
    assert response.status_code == 403


def test_list_workspaces_ok(sa_client: TestClient, monkeypatch) -> None:
    """Super-admin can list workspaces under a tenant."""

    monkeypatch.setattr(
        "app.sys.tenant.api.router.svc.list_workspaces_page",
        AsyncMock(return_value=([], 0)),
    )
    response = sa_client.get(f"/sys/tenants/{TENANT_ID}/workspaces")
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_delete_workspace_ok(sa_client: TestClient, monkeypatch) -> None:
    """Super-admin can delete a workspace row."""

    delete_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.sys.tenant.api.router.svc.delete_workspace",
        delete_mock,
    )
    response = sa_client.delete(
        f"/sys/tenants/{TENANT_ID}/workspaces/{WORKSPACE_ID}"
    )
    assert response.status_code == 204
    delete_mock.assert_awaited_once()


def test_create_workspace_ok(sa_client: TestClient, monkeypatch) -> None:
    """Super-admin can create a workspace."""

    row = Workspace(
        id=WORKSPACE_ID,
        tenant_id=TENANT_ID,
        name="Default",
        slug="default",
        status=True,
        remark=None,
    )
    monkeypatch.setattr(
        "app.sys.tenant.api.router.svc.create_workspace",
        AsyncMock(return_value=row),
    )
    response = sa_client.post(
        f"/sys/tenants/{TENANT_ID}/workspaces",
        json={"name": "Default", "slug": "default", "status": True},
    )
    assert response.status_code == 201
    assert response.json()["tenant_id"] == str(TENANT_ID)
