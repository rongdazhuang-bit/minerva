"""Integration tests for /sys/tenants routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.domain.identity.models import Tenant, User
from app.errors import register_exception_handlers
from app.exceptions import AppError
from app.sys.tenant.api.deps import require_super_admin
from app.sys.tenant.api.router import router as tenants_router

TENANT_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c1")


async def _deny_super_admin() -> User:
    """Simulate non-super-admin access."""

    raise AppError("auth.forbidden", "Not super admin", 403)


async def _allow_super_admin() -> User:
    """Simulate super-admin access."""

    return User(
        id=uuid.uuid4(),
        email="sa@example.com",
        password_hash="x",
        nickname="Super Admin",
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


def test_list_forbidden_for_non_super_admin(forbidden_client: TestClient) -> None:
    """Non-super-admin users cannot list tenants."""

    response = forbidden_client.get("/sys/tenants")
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


def test_list_ok(sa_client: TestClient, monkeypatch) -> None:
    """Super-admin can list tenants."""

    monkeypatch.setattr(
        "app.sys.tenant.api.router.svc.list_tenants_page",
        AsyncMock(return_value=([], 0)),
    )
    response = sa_client.get("/sys/tenants")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_create_ok(sa_client: TestClient, monkeypatch) -> None:
    """Super-admin can create a tenant."""

    row = Tenant(id=TENANT_ID, name="Acme", slug="acme", status=True, remark=None)
    monkeypatch.setattr(
        "app.sys.tenant.api.router.svc.create_tenant",
        AsyncMock(return_value=row),
    )
    response = sa_client.post(
        "/sys/tenants",
        json={"name": "Acme", "slug": "acme", "status": True},
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "acme"


def test_delete_ok(sa_client: TestClient, monkeypatch) -> None:
    """Super-admin can delete a tenant."""

    monkeypatch.setattr(
        "app.sys.tenant.api.router.svc.delete_tenant",
        AsyncMock(return_value=None),
    )
    response = sa_client.delete(f"/sys/tenants/{TENANT_ID}")
    assert response.status_code == 204
