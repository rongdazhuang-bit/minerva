"""Unit and service-layer tests for role_service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.exceptions import AppError
from app.sys.menu.domain.db.models import SysMenu
from app.sys.role.domain.db.models import SysRole
from app.sys.role.service import role_service as svc


def _role_row(
    *,
    role_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    role_key: str = "admin",
) -> SysRole:
    """Build a minimal SysRole instance for tests."""

    return SysRole(
        id=role_id or uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        role_name="管理员",
        role_key=role_key,
        role_sort=0,
        status=True,
        create_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_create_role_rejects_invalid_menu_ids(monkeypatch) -> None:
    """Creating with unknown menu ids raises role.invalid_menu_ids."""

    session = AsyncMock()
    bad_id = uuid.uuid4()

    async def fake_list_all(_session: object) -> list[SysMenu]:
        return []

    monkeypatch.setattr("app.sys.role.service.role_service.menu_repo.list_all", fake_list_all)

    with pytest.raises(AppError) as exc:
        await svc.create_role(
            session,
            workspace_id=uuid.uuid4(),
            data={
                "role_name": "r",
                "role_key": "k",
                "menu_ids": [bad_id],
            },
        )
    assert exc.value.code == "role.invalid_menu_ids"


@pytest.mark.asyncio
async def test_create_role_conflict_on_duplicate_role_key(monkeypatch) -> None:
    """IntegrityError on unique role_key maps to role.conflict."""

    session = AsyncMock()
    row = _role_row()

    async def fake_add(_session: object, _row: SysRole) -> SysRole:
        return row

    async def fake_commit_or_conflict(_session: object) -> None:
        raise AppError("role.conflict", "Duplicate role_key in workspace", 409)

    monkeypatch.setattr("app.sys.role.service.role_service.repo.add_role", fake_add)
    monkeypatch.setattr(
        "app.sys.role.service.role_service._commit_or_conflict",
        fake_commit_or_conflict,
    )

    with pytest.raises(AppError) as exc:
        await svc.create_role(
            session,
            workspace_id=row.workspace_id,
            data={"role_name": "r", "role_key": "admin", "menu_ids": []},
        )
    assert exc.value.code == "role.conflict"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_get_role_wrong_workspace_returns_not_found(monkeypatch) -> None:
    """Role in another workspace returns role.not_found."""

    session = AsyncMock()
    ws = uuid.uuid4()
    role_id = uuid.uuid4()

    async def fake_get_for_workspace(
        _session: object, *, workspace_id: uuid.UUID, role_id: uuid.UUID
    ) -> SysRole | None:
        return None

    monkeypatch.setattr(
        "app.sys.role.service.role_service.repo.get_role_for_workspace",
        fake_get_for_workspace,
    )

    with pytest.raises(AppError) as exc:
        await svc.get_role_detail(session, workspace_id=ws, role_id=role_id)
    assert exc.value.code == "role.not_found"
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_role_removes_menus_first(monkeypatch) -> None:
    """Delete removes menu links before deleting the role row."""

    session = AsyncMock()
    ws = uuid.uuid4()
    role_id = uuid.uuid4()
    row = _role_row(role_id=role_id, workspace_id=ws)
    calls: list[str] = []

    async def fake_require(
        _session: object, *, workspace_id: uuid.UUID, role_id: uuid.UUID
    ) -> SysRole:
        return row

    async def fake_delete_menus(_session: object, role_id: uuid.UUID) -> None:
        calls.append("menus")

    async def fake_delete_role(_session: object, role_id: uuid.UUID) -> None:
        calls.append("role")

    async def fake_commit() -> None:
        calls.append("commit")

    monkeypatch.setattr("app.sys.role.service.role_service._require_role", fake_require)
    monkeypatch.setattr(
        "app.sys.role.service.role_service.repo.delete_role_menus", fake_delete_menus
    )
    monkeypatch.setattr(
        "app.sys.role.service.role_service.repo.delete_role", fake_delete_role
    )
    monkeypatch.setattr(session, "commit", fake_commit)

    await svc.delete_role(session, workspace_id=ws, role_id=role_id)
    assert calls == ["menus", "role", "commit"]


def test_is_unique_violation_detects_pgcode() -> None:
    """Unique violation helper recognizes PostgreSQL 23505."""

    class Orig:
        pgcode = "23505"

    exc = IntegrityError("stmt", {}, Orig())
    assert svc._is_unique_violation(exc) is True
