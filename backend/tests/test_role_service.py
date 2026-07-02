"""Unit tests for role service menu tree helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.exceptions import AppError
from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.role.service import role_service as svc


def test_collect_menu_ids_with_ancestors_includes_parents() -> None:
    """Authorized leaf menus should pull in ancestor ids for display."""

    root = uuid.uuid4()
    child = uuid.uuid4()
    leaf = uuid.uuid4()
    nodes = [
        SysMenuNodeOut(
            id=root,
            parent_id=None,
            menu_name="Settings",
            menu_type="M",
            path="/settings",
            perms=None,
            icon=None,
            order_num=1,
            status=True,
            visible=True,
            is_external=False,
            children=[
                SysMenuNodeOut(
                    id=child,
                    parent_id=root,
                    menu_name="Users",
                    menu_type="C",
                    path="users",
                    perms=None,
                    icon=None,
                    order_num=1,
                    status=True,
                    visible=True,
                    is_external=False,
                    children=[
                        SysMenuNodeOut(
                            id=leaf,
                            parent_id=child,
                            menu_name="List",
                            menu_type="F",
                            path=None,
                            perms="user:list",
                            icon=None,
                            order_num=1,
                            status=True,
                            visible=True,
                            is_external=False,
                            children=[],
                        )
                    ],
                )
            ],
        )
    ]
    display_ids = svc.collect_menu_display_ids(authorized_ids=[leaf], tree_nodes=nodes)
    assert display_ids == {root, child, leaf}


def test_filter_menu_ids_to_tenant_authorized_strips_ancestor_only() -> None:
    """Persist only tenant-authorized menu ids even if ancestors were checked."""

    root = uuid.uuid4()
    leaf = uuid.uuid4()
    authorized = {leaf}
    submitted = [root, leaf]
    filtered = svc.filter_menu_ids_to_tenant_authorized(
        menu_ids=submitted,
        authorized_ids=authorized,
    )
    assert filtered == [leaf]


def test_resolve_menu_ids_for_tenant_persist_strips_ancestor_only() -> None:
    """Ancestor ids in the display tree are filtered, not rejected."""

    root = uuid.uuid4()
    child = uuid.uuid4()
    leaf = uuid.uuid4()
    authorized = {leaf}
    display = {root, child, leaf}
    result = svc.resolve_menu_ids_for_tenant_persist(
        menu_ids=[root, child, leaf],
        authorized_ids=authorized,
        display_ids=display,
    )
    assert result == [leaf]


def test_resolve_menu_ids_for_tenant_persist_rejects_outside_display_tree() -> None:
    """Menu ids outside the tenant display tree are rejected."""

    root = uuid.uuid4()
    leaf = uuid.uuid4()
    outsider = uuid.uuid4()
    authorized = {leaf}
    display = {root, leaf}

    with pytest.raises(AppError) as exc_info:
        svc.resolve_menu_ids_for_tenant_persist(
            menu_ids=[outsider],
            authorized_ids=authorized,
            display_ids=display,
        )

    assert exc_info.value.code == "role.menu_not_in_tenant"
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_menu_ids_in_tenant_filters_ancestor_ids(monkeypatch) -> None:
    """Service validation strips ancestor-only ids before role persistence."""

    session = AsyncMock()
    tenant_id = uuid.uuid4()
    root = uuid.uuid4()
    leaf = uuid.uuid4()

    async def fake_list_tenant_menu_ids(_session, *, tenant_id: uuid.UUID) -> list[uuid.UUID]:
        return [leaf]

    async def fake_list_menu_tree(_session) -> list[SysMenuNodeOut]:
        return [
            SysMenuNodeOut(
                id=root,
                parent_id=None,
                menu_name="Root",
                menu_type="M",
                path="/root",
                perms=None,
                icon=None,
                order_num=1,
                status=True,
                visible=True,
                is_external=False,
                children=[
                    SysMenuNodeOut(
                        id=leaf,
                        parent_id=root,
                        menu_name="Leaf",
                        menu_type="C",
                        path="leaf",
                        perms=None,
                        icon=None,
                        order_num=1,
                        status=True,
                        visible=True,
                        is_external=False,
                        children=[],
                    )
                ],
            )
        ]

    monkeypatch.setattr(
        "app.sys.role.service.role_service.list_tenant_menu_ids",
        fake_list_tenant_menu_ids,
    )
    monkeypatch.setattr(
        "app.sys.role.service.role_service.list_menu_tree_for_role_assignment",
        fake_list_menu_tree,
    )
    monkeypatch.setattr(
        "app.sys.role.service.role_service._validate_menu_ids",
        AsyncMock(return_value=None),
    )

    result = await svc._validate_menu_ids_in_tenant(
        session,
        tenant_id=tenant_id,
        menu_ids=[root, leaf],
    )
    assert result == [leaf]


@pytest.mark.asyncio
async def test_list_menu_tree_for_tenant_empty_when_no_permissions(monkeypatch) -> None:
    """Tenants without menu permissions receive an empty role menu tree."""

    session = AsyncMock()
    tenant_id = uuid.uuid4()

    async def fake_list_tenant_menu_ids(_session, *, tenant_id: uuid.UUID) -> list[uuid.UUID]:
        return []

    monkeypatch.setattr(
        "app.sys.role.service.role_service.list_tenant_menu_ids",
        fake_list_tenant_menu_ids,
    )

    tree = await svc.list_menu_tree_for_tenant_role_assignment(
        session,
        tenant_id=tenant_id,
    )
    assert tree == []
