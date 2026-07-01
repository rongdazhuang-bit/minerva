"""Business logic for global sys_menu CRUD and tree assembly."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization.repository import load_enabled_tenant_menu_ids
from app.core.domain.identity.models import User, Workspace
from app.exceptions import AppError
from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.menu.domain.db.models import SysMenu
from app.sys.menu.infrastructure import repository as repo
from app.sys.menu.utils.menu_tree import build_menu_tree
from app.sys.role.infrastructure import repository as role_repo
from app.sys.user.infrastructure import repository as user_repo


def _utc_now() -> datetime:
    return datetime.now(UTC)


def collect_descendant_ids(
    parent_to_children: dict[uuid.UUID, list[uuid.UUID]],
    root: uuid.UUID,
) -> set[uuid.UUID]:
    """Collect all descendant ids under root (excluding root itself)."""

    out: set[uuid.UUID] = set()
    stack = list(parent_to_children.get(root, []))
    while stack:
        cid = stack.pop()
        if cid in out:
            continue
        out.add(cid)
        stack.extend(parent_to_children.get(cid, []))
    return out


def _build_parent_map(rows: list[SysMenu]) -> dict[uuid.UUID, list[uuid.UUID]]:
    m: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for row in rows:
        if row.parent_id is not None:
            m[row.parent_id].append(row.id)
    return m


def validate_hierarchy(
    *,
    menu_type: str,
    path: str | None,
    perms: str | None,
    parent: SysMenu | None,
) -> None:
    """Validate menu type, required fields, and parent-child rules."""

    if menu_type not in ("M", "C", "F"):
        raise AppError("menu.invalid_hierarchy", "menu_type must be M, C, or F", 400)
    if menu_type == "C" and not (path and path.strip()):
        raise AppError("menu.path_required", "Menu type C requires path", 400)
    if menu_type == "F" and not (perms and perms.strip()):
        raise AppError("menu.perms_required", "Menu type F requires perms", 400)
    if parent is not None:
        if menu_type == "F" and parent.menu_type != "C":
            raise AppError("menu.invalid_hierarchy", "Button must be under menu C", 400)
        if menu_type == "C" and parent.menu_type not in ("M", "C"):
            raise AppError("menu.invalid_hierarchy", "Menu C must be under directory M or menu C", 400)
        if menu_type in ("M", "C") and parent.menu_type == "F":
            raise AppError("menu.invalid_hierarchy", "Cannot place under button F", 400)


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "pgcode", None) == "23505":
        return True
    return "unique" in str(exc).lower()


async def _commit_or_conflict(session: AsyncSession) -> None:
    """Commit or map unique violations to menu.conflict."""

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if _is_unique_violation(e):
            raise AppError(
                "menu.conflict",
                "Duplicate menu_key",
                409,
            ) from e
        raise


def filter_nav_rows(rows: list[SysMenu]) -> list[SysMenu]:
    """Keep only sidebar-eligible rows (M/C, visible, enabled)."""

    return [
        r
        for r in rows
        if r.menu_type in ("M", "C") and r.visible and r.status
    ]


def expand_allowed_nav_menu_ids(
    all_rows: list[SysMenu],
    granted_menu_ids: set[uuid.UUID],
) -> set[uuid.UUID]:
    """Expand role-granted menu ids to sidebar M/C nodes and ancestor directories."""

    by_id = {r.id: r for r in all_rows}
    keep: set[uuid.UUID] = set()
    for menu_id in granted_menu_ids:
        cur = by_id.get(menu_id)
        while cur is not None:
            if cur.menu_type in ("M", "C"):
                keep.add(cur.id)
            if cur.parent_id is None:
                break
            cur = by_id.get(cur.parent_id)
    return keep


def filter_rows_by_menu_ids(
    rows: list[SysMenu],
    allowed_ids: set[uuid.UUID],
) -> list[SysMenu]:
    """Keep rows whose id is in the allowed set."""

    if not allowed_ids:
        return []
    return [r for r in rows if r.id in allowed_ids]


def _assert_no_cycle(
    *,
    menu_id: uuid.UUID,
    new_parent_id: uuid.UUID | None,
    parent_map: dict[uuid.UUID, list[uuid.UUID]],
) -> None:
    """Reject parent assignment that would create a cycle."""

    if new_parent_id is None:
        return
    if new_parent_id == menu_id:
        raise AppError("menu.cycle", "Menu cannot be its own parent", 400)
    descendants = collect_descendant_ids(parent_map, menu_id)
    if new_parent_id in descendants:
        raise AppError("menu.cycle", "Cannot set a descendant as parent", 400)


def _filter_rows(
    rows: list[SysMenu],
    *,
    menu_name: str | None,
    status: bool | None,
) -> list[SysMenu]:
    """Apply list filters; keeps ancestors of matched nodes for tree display."""

    if not menu_name and status is None:
        return rows
    name_q = menu_name.strip().lower() if menu_name else None
    by_id = {r.id: r for r in rows}
    matched: set[uuid.UUID] = set()
    for r in rows:
        if status is not None and r.status != status:
            continue
        if name_q and name_q not in r.menu_name.lower():
            continue
        matched.add(r.id)
    if not matched:
        return []
    keep: set[uuid.UUID] = set()
    for mid in matched:
        cur: SysMenu | None = by_id.get(mid)
        while cur is not None:
            if cur.id in keep:
                break
            keep.add(cur.id)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
    return [r for r in rows if r.id in keep]


async def list_menu_tree(
    session: AsyncSession,
    *,
    menu_name: str | None = None,
    status: bool | None = None,
) -> list[SysMenuNodeOut]:
    """Return full admin tree with optional filters."""

    rows = await repo.list_all(session)
    filtered = _filter_rows(rows, menu_name=menu_name, status=status)
    return build_menu_tree(filtered)


async def list_nav_tree(session: AsyncSession) -> list[SysMenuNodeOut]:
    """Return sidebar tree: M/C only, visible and enabled."""

    rows = await repo.list_all(session)
    return build_menu_tree(filter_nav_rows(rows))


async def list_nav_tree_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> list[SysMenuNodeOut]:
    """Return sidebar tree filtered by the user's enabled roles in the workspace."""

    user = await session.get(User, user_id)
    if user is None:
        return []

    ws = await session.get(Workspace, workspace_id)
    tenant_id = ws.tenant_id if ws is not None else None
    from app.core.security.permission_resolver import build_permission_context

    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    rows = await repo.list_all(session)
    nav_rows = filter_nav_rows(rows)
    if ctx.is_super_admin:
        return build_menu_tree(nav_rows)

    tenant_menu_ids: set[uuid.UUID] = set()
    if tenant_id is not None:
        tenant_menu_ids = set(
            await load_enabled_tenant_menu_ids(session, tenant_id=tenant_id)
        )

    role_expanded = expand_allowed_nav_menu_ids(nav_rows, set(ctx.menu_ids))
    if tenant_id is not None and tenant_menu_ids:
        tenant_expanded = expand_allowed_nav_menu_ids(nav_rows, tenant_menu_ids)
        allowed = role_expanded & tenant_expanded
    else:
        allowed = role_expanded

    return build_menu_tree(filter_rows_by_menu_ids(nav_rows, allowed))


async def create_menu(session: AsyncSession, data: dict[str, Any]) -> SysMenu:
    """Create a menu after hierarchy validation."""

    parent: SysMenu | None = None
    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent = await repo.get_by_id(session, parent_id)
        if parent is None:
            raise AppError("menu.parent_not_found", "Parent menu not found", 400)
    menu_type = str(data["menu_type"])
    validate_hierarchy(
        menu_type=menu_type,
        path=data.get("path"),
        perms=data.get("perms"),
        parent=parent,
    )
    now = _utc_now()
    row = SysMenu(
        parent_id=parent_id,
        menu_name=data["menu_name"],
        i18n_key=data.get("i18n_key"),
        menu_key=data.get("menu_key"),
        order_num=int(data.get("order_num") or 0),
        path=data.get("path"),
        menu_type=menu_type,
        perms=data.get("perms"),
        icon=data.get("icon"),
        visible=bool(data.get("visible", True)),
        status=bool(data.get("status", True)),
        is_external=bool(data.get("is_external", False)),
        remark=data.get("remark"),
        create_at=now,
        update_at=now,
    )
    await repo.add(session, row)
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def update_menu(
    session: AsyncSession,
    menu_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysMenu:
    """Patch a menu row with cycle and hierarchy checks."""

    row = await repo.get_by_id(session, menu_id)
    if row is None:
        raise AppError("menu.not_found", "Menu not found", 404)
    all_rows = await repo.list_all(session)
    parent_map = _build_parent_map(all_rows)

    new_parent_id = patch["parent_id"] if "parent_id" in patch else row.parent_id
    if "parent_id" in patch:
        _assert_no_cycle(menu_id=menu_id, new_parent_id=new_parent_id, parent_map=parent_map)

    parent: SysMenu | None = None
    if new_parent_id is not None:
        parent = await repo.get_by_id(session, new_parent_id)
        if parent is None:
            raise AppError("menu.parent_not_found", "Parent menu not found", 400)

    menu_type = patch.get("menu_type", row.menu_type)
    path = patch.get("path", row.path)
    perms = patch.get("perms", row.perms)
    validate_hierarchy(menu_type=menu_type, path=path, perms=perms, parent=parent)

    for key, value in patch.items():
        setattr(row, key, value)
    row.update_at = _utc_now()
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def delete_menu_cascade(session: AsyncSession, menu_id: uuid.UUID) -> int:
    """Delete a menu and all descendants; returns total deleted count."""

    row = await repo.get_by_id(session, menu_id)
    if row is None:
        raise AppError("menu.not_found", "Menu not found", 404)
    all_rows = await repo.list_all(session)
    parent_map = _build_parent_map(all_rows)
    descendants = collect_descendant_ids(parent_map, menu_id)
    ids = list(descendants | {menu_id})
    await repo.delete_by_ids(session, ids)
    await session.commit()
    return len(ids)


async def count_descendants(session: AsyncSession, menu_id: uuid.UUID) -> int:
    """Return number of descendant rows (excluding the node itself)."""

    all_rows = await repo.list_all(session)
    parent_map = _build_parent_map(all_rows)
    return len(collect_descendant_ids(parent_map, menu_id))
