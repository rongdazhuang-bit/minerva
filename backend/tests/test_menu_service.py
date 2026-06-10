"""Unit and service-layer tests for menu_service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exceptions import AppError
from app.sys.menu.domain.db.models import SysMenu
from app.sys.menu.service import menu_service as svc


def _menu_row(
    *,
    id: uuid.UUID,
    parent_id: uuid.UUID | None = None,
    menu_type: str = "C",
    menu_name: str = "n",
    path: str | None = "/app/x",
    visible: bool = True,
    status: bool = True,
) -> SysMenu:
    return SysMenu(
        id=id,
        parent_id=parent_id,
        menu_name=menu_name,
        menu_type=menu_type,
        order_num=0,
        path=path,
        visible=visible,
        status=status,
        is_external=False,
        create_at=datetime.now(UTC),
    )


def test_collect_descendant_ids_deep() -> None:
    a, b, c, d = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    parent_map = {a: [b], b: [c, d]}
    got = svc.collect_descendant_ids(parent_map, a)
    assert got == {b, c, d}


def test_validate_hierarchy_c_requires_path() -> None:
    with pytest.raises(AppError) as exc:
        svc.validate_hierarchy(menu_type="C", path=None, perms=None, parent=None)
    assert exc.value.code == "menu.path_required"


def test_validate_hierarchy_f_requires_perms() -> None:
    with pytest.raises(AppError) as exc:
        svc.validate_hierarchy(menu_type="F", path=None, perms=None, parent=None)
    assert exc.value.code == "menu.perms_required"


def test_validate_hierarchy_c_parent_must_be_m_or_c() -> None:
    parent = _menu_row(id=uuid.uuid4(), menu_type="F", path=None)
    with pytest.raises(AppError) as exc:
        svc.validate_hierarchy(menu_type="C", path="/app/a", perms=None, parent=parent)
    assert exc.value.code == "menu.invalid_hierarchy"


def test_filter_nav_rows_excludes_f_hidden_and_disabled() -> None:
    rows = [
        _menu_row(id=uuid.uuid4(), menu_type="M", path=None),
        _menu_row(id=uuid.uuid4(), menu_type="C"),
        _menu_row(id=uuid.uuid4(), menu_type="F", path=None),
        _menu_row(id=uuid.uuid4(), menu_type="C", visible=False),
        _menu_row(id=uuid.uuid4(), menu_type="C", status=False),
    ]
    nav = svc.filter_nav_rows(rows)
    assert len(nav) == 2
    assert all(r.menu_type in ("M", "C") and r.visible and r.status for r in nav)


@pytest.mark.asyncio
async def test_delete_menu_cascade_returns_deleted_count(monkeypatch) -> None:
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    root = _menu_row(id=root_id, menu_type="M", path=None, menu_name="root")
    child = _menu_row(id=child_id, parent_id=root_id, menu_name="child")

    session = AsyncMock()

    async def fake_get_by_id(_session: object, menu_id: uuid.UUID) -> SysMenu | None:
        if menu_id == root_id:
            return root
        return None

    async def fake_list_all(_session: object) -> list[SysMenu]:
        return [root, child]

    deleted: list[uuid.UUID] = []

    async def fake_delete_by_ids(_session: object, ids: list[uuid.UUID]) -> int:
        deleted.extend(ids)
        return len(ids)

    monkeypatch.setattr(svc.repo, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(svc.repo, "list_all", fake_list_all)
    monkeypatch.setattr(svc.repo, "delete_by_ids", fake_delete_by_ids)

    count = await svc.delete_menu_cascade(session, root_id)
    assert count == 2
    assert set(deleted) == {root_id, child_id}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_menu_menu_key_conflict(monkeypatch) -> None:
    from sqlalchemy.exc import IntegrityError

    session = AsyncMock()
    session.refresh = AsyncMock()

    async def fake_add(_session: object, row: SysMenu) -> SysMenu:
        return row

    async def fail_commit():
        raise IntegrityError("insert", {}, Exception("duplicate key value violates unique constraint"))

    session.commit = AsyncMock(side_effect=fail_commit)
    session.rollback = AsyncMock()

    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "add", fake_add)

    with pytest.raises(AppError) as exc:
        await svc.create_menu(
            session,
            {
                "menu_name": "Dup",
                "menu_type": "M",
                "menu_key": "overview",
                "order_num": 0,
            },
        )
    assert exc.value.code == "menu.conflict"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_nav_tree_builds_filtered_tree(monkeypatch) -> None:
    root_id = uuid.uuid4()
    rows = [
        _menu_row(id=root_id, menu_type="M", path=None, menu_name="Root"),
        _menu_row(id=uuid.uuid4(), parent_id=root_id, menu_type="C", menu_name="Child"),
        _menu_row(id=uuid.uuid4(), menu_type="F", path=None),
    ]
    session = MagicMock()

    async def fake_list_all(_session: object) -> list[SysMenu]:
        return rows

    monkeypatch.setattr(svc.repo, "list_all", fake_list_all)
    tree = await svc.list_nav_tree(session)
    assert len(tree) == 1
    assert tree[0].menu_name == "Root"
    assert len(tree[0].children) == 1
    assert tree[0].children[0].menu_name == "Child"
