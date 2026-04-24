from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tool.ocr.domain.db.models import SysOcrTool


async def list_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysOcrTool]:
    result = await session.execute(
        select(SysOcrTool)
        .where(SysOcrTool.workspace_id == workspace_id)
        .order_by(SysOcrTool.create_at.desc(), SysOcrTool.id.desc())
    )
    return result.scalars().all()


async def get_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
) -> SysOcrTool | None:
    result = await session.execute(
        select(SysOcrTool).where(
            SysOcrTool.id == tool_id,
            SysOcrTool.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()
