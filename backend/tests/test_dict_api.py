"""Integration tests for global /sys/dicts routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.errors import register_exception_handlers
from app.exceptions import AppError
from app.sys.dict.api.deps import require_any_workspace_member
from app.sys.dict.api.router import router as dicts_router
from app.sys.tenant.api.deps import require_super_admin

FAKE_USER = User(
    id=uuid.uuid4(),
    email="u@example.com",
    password_hash="x",
    nickname="U",
    is_super_admin=False,
)


async def _allow_reader() -> User:
    return FAKE_USER


async def _deny_reader() -> User:
    raise AppError("auth.forbidden", "denied", 403)


async def _allow_super_admin() -> User:
    return User(
        id=FAKE_USER.id,
        email="sa@example.com",
        password_hash="x",
        nickname="SA",
        is_super_admin=True,
    )


async def _deny_super_admin() -> User:
    raise AppError("auth.forbidden", "denied", 403)


def _make_dict_app(*, reader: bool, writer: bool) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(dicts_router)
    app.dependency_overrides[require_any_workspace_member] = (
        _allow_reader if reader else _deny_reader
    )
    app.dependency_overrides[require_super_admin] = (
        _allow_super_admin if writer else _deny_super_admin
    )
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    return app


@pytest.fixture
def reader_client() -> Iterator[TestClient]:
    with patch(
        "app.sys.dict.api.router.svc.list_dicts_page",
        new=AsyncMock(return_value=([], 0)),
    ):
        yield TestClient(_make_dict_app(reader=True, writer=False))


def test_list_dicts_forbidden_without_reader() -> None:
    client = TestClient(_make_dict_app(reader=False, writer=False))
    r = client.get("/sys/dicts")
    assert r.status_code == 403


def test_list_dicts_ok_for_reader(reader_client: TestClient) -> None:
    r = reader_client.get("/sys/dicts")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}


def test_create_dict_forbidden_for_non_super_admin() -> None:
    with patch(
        "app.sys.dict.api.router.svc.create_dict",
        new=AsyncMock(),
    ):
        client = TestClient(_make_dict_app(reader=True, writer=False))
        r = client.post(
            "/sys/dicts",
            json={"dict_code": "TEST", "dict_name": "Test"},
        )
        assert r.status_code == 403
