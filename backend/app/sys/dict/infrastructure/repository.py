from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.dict.domain.db.models import SysDict, SysDictItem


async def list_dicts_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysDict]:
    result = await session.execute(
        select(SysDict)
        .where(SysDict.workspace_id == workspace_id)
        .order_by(SysDict.create_at.desc(), SysDict.dict_sort.desc())
    )
    return result.scalars().all()


async def get_dict_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
) -> SysDict | None:
    result = await session.execute(
        select(SysDict).where(
            SysDict.id == dict_id,
            SysDict.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def list_items_for_dict(
    session: AsyncSession,
    *,
    dict_uuid: uuid.UUID,
) -> Sequence[SysDictItem]:
    result = await session.execute(
        select(SysDictItem)
        .where(SysDictItem.dict_uuid == dict_uuid)
        .order_by(SysDictItem.item_sort.desc().nulls_last(), SysDictItem.code.asc())
    )
    return result.scalars().all()


async def get_item_in_dict(
    session: AsyncSession,
    *,
    dict_uuid: uuid.UUID,
    item_id: uuid.UUID,
) -> SysDictItem | None:
    result = await session.execute(
        select(SysDictItem).where(
            SysDictItem.id == item_id,
            SysDictItem.dict_uuid == dict_uuid,
        )
    )
    return result.scalar_one_or_none()


async def count_direct_children(
    session: AsyncSession,
    *,
    dict_uuid: uuid.UUID,
    parent_id: uuid.UUID,
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(SysDictItem)
        .where(
            SysDictItem.dict_uuid == dict_uuid,
            SysDictItem.parent_uuid == parent_id,
        )
    )
    return int(result.scalar_one() or 0)
