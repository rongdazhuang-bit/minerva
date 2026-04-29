"""Lightweight queries listing catalog ``SysModel`` rows."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.model_provider.domain.db.models import SysModel


async def list_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysModel]:
    result = await session.execute(
        select(SysModel)
        .where(SysModel.workspace_id == workspace_id)
        .order_by(SysModel.create_at.desc().nulls_last(), SysModel.id.desc())
    )
    return result.scalars().all()


async def get_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID, model_id: uuid.UUID
) -> SysModel | None:
    result = await session.execute(
        select(SysModel).where(
            SysModel.id == model_id,
            SysModel.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()
