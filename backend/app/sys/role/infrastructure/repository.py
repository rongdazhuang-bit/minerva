"""Async queries for sys_role and sys_role_menu."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.role.domain.db.models import SysRole, SysRoleMenu


def _role_list_order():
    """Sort roles by display order then creation time."""

    return (SysRole.role_sort.asc(), SysRole.create_at.desc())


async def count_roles_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> int:
    """Count roles in a workspace matching optional filters."""

    stmt = select(func.count()).select_from(SysRole).where(
        SysRole.workspace_id == workspace_id
    )
    if role_name:
        stmt = stmt.where(SysRole.role_name.ilike(f"%{role_name.strip()}%"))
    if status is not None:
        stmt = stmt.where(SysRole.status == status)
    if role_key:
        stmt = stmt.where(SysRole.role_key == role_key.strip())
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_roles_for_workspace_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> Sequence[SysRole]:
    """Return one page of roles for a workspace."""

    stmt = (
        select(SysRole)
        .where(SysRole.workspace_id == workspace_id)
        .order_by(*_role_list_order())
        .limit(limit)
        .offset(offset)
    )
    if role_name:
        stmt = stmt.where(SysRole.role_name.ilike(f"%{role_name.strip()}%"))
    if status is not None:
        stmt = stmt.where(SysRole.status == status)
    if role_key:
        stmt = stmt.where(SysRole.role_key == role_key.strip())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_role_by_id(
    session: AsyncSession, role_id: uuid.UUID
) -> SysRole | None:
    """Load one role by primary key."""

    return await session.get(SysRole, role_id)


async def get_role_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
) -> SysRole | None:
    """Load a role only when it belongs to the given workspace."""

    result = await session.execute(
        select(SysRole).where(
            SysRole.id == role_id,
            SysRole.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def add_role(session: AsyncSession, row: SysRole) -> SysRole:
    """Insert a role row and flush."""

    session.add(row)
    await session.flush()
    return row


async def delete_role(session: AsyncSession, role_id: uuid.UUID) -> None:
    """Delete one role row."""

    row = await session.get(SysRole, role_id)
    if row is not None:
        await session.delete(row)
        await session.flush()


async def list_menu_ids_for_role(
    session: AsyncSession, role_id: uuid.UUID
) -> list[uuid.UUID]:
    """Return menu ids linked to a role."""

    result = await session.execute(
        select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == role_id)
    )
    return list(result.scalars().all())


async def delete_role_menus(session: AsyncSession, role_id: uuid.UUID) -> None:
    """Remove all menu links for a role."""

    await session.execute(delete(SysRoleMenu).where(SysRoleMenu.role_id == role_id))
    await session.flush()


async def replace_role_menus(
    session: AsyncSession,
    *,
    role_id: uuid.UUID,
    menu_ids: list[uuid.UUID],
) -> None:
    """Replace all menu links for a role with the given id list."""

    await delete_role_menus(session, role_id=role_id)
    for menu_id in menu_ids:
        session.add(SysRoleMenu(role_id=role_id, menu_id=menu_id))
    await session.flush()
