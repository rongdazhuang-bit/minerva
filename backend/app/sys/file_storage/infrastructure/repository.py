"""Persistence queries for ``SysStorage`` workspace CRUD."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.file_storage.domain.db.models import SysStorage


def _storage_order():
    """Return default list ordering for file storage rows."""

    return (
        SysStorage.create_at.desc().nulls_last(),
        SysStorage.id.desc(),
    )


async def count_for_workspace(session: AsyncSession, *, workspace_id: uuid.UUID) -> int:
    """Count file storage rows under one workspace."""

    result = await session.execute(
        select(func.count()).select_from(SysStorage).where(
            SysStorage.workspace_id == workspace_id
        )
    )
    return int(result.scalar_one() or 0)


async def list_for_workspace_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
) -> Sequence[SysStorage]:
    """List paginated file storage rows by workspace."""

    result = await session.execute(
        select(SysStorage)
        .where(SysStorage.workspace_id == workspace_id)
        .order_by(*_storage_order())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID, storage_id: uuid.UUID
) -> SysStorage | None:
    """Fetch one storage row by id within workspace scope."""

    result = await session.execute(
        select(SysStorage).where(
            SysStorage.workspace_id == workspace_id,
            SysStorage.id == storage_id,
        )
    )
    return result.scalar_one_or_none()
