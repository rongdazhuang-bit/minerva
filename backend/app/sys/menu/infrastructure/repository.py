"""Persistence helpers for sys_menu."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.menu.domain.db.models import SysMenu


async def list_all(session: AsyncSession) -> list[SysMenu]:
    """Return every menu row."""

    r = await session.execute(select(SysMenu))
    return list(r.scalars().all())


async def get_by_id(session: AsyncSession, menu_id: uuid.UUID) -> SysMenu | None:
    """Load one menu by primary key."""

    return await session.get(SysMenu, menu_id)


async def add(session: AsyncSession, row: SysMenu) -> SysMenu:
    """Insert a menu row and flush."""

    session.add(row)
    await session.flush()
    return row


async def delete_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> int:
    """Delete menus by id list; returns affected row count."""

    if not ids:
        return 0
    r = await session.execute(delete(SysMenu).where(SysMenu.id.in_(ids)))
    return int(r.rowcount or 0)
