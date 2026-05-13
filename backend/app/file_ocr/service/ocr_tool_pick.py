"""Select the default ``sys_ocr_tool`` row for one workspace and OCR engine type."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.tool.ocr.domain.db.models import SysOcrTool


async def select_default_ocr_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    ocr_type: str,
) -> SysOcrTool | None:
    """Return the newest configured tool row for ``ocr_type`` within a workspace.

    When several tools share the same ``ocr_type``, pick the row with the greatest
    ``update_at`` (falling back to ``create_at`` then ``id``) so operators can steer
    defaults by touching the row they want active.
    """

    stmt = (
        select(SysOcrTool)
        .where(
            SysOcrTool.workspace_id == workspace_id,
            SysOcrTool.ocr_type == ocr_type,
        )
        .order_by(
            SysOcrTool.update_at.desc().nulls_last(),
            SysOcrTool.create_at.desc().nulls_last(),
            SysOcrTool.id.desc(),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
