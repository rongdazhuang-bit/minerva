from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.tool.ocr.domain.db.models import SysOcrTool
from app.tool.ocr.infrastructure import repository as repo


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def list_tools(session: AsyncSession, *, workspace_id: uuid.UUID) -> list[SysOcrTool]:
    return list(await repo.list_for_workspace(session, workspace_id=workspace_id))


async def get_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
) -> SysOcrTool:
    row = await repo.get_for_workspace(
        session,
        workspace_id=workspace_id,
        tool_id=tool_id,
    )
    if row is None:
        raise AppError("ocr_tool.not_found", "OCR tool not found", 404)
    return row


async def create_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    url: str,
    auth_type: str | None,
    user_name: str | None,
    user_passwd: str | None,
    api_key: str | None,
    remark: str | None,
) -> SysOcrTool:
    now = _utc_now()
    row = SysOcrTool(
        workspace_id=workspace_id,
        name=name.strip(),
        url=url.strip(),
        auth_type=auth_type,
        user_name=user_name,
        user_passwd=user_passwd,
        api_key=api_key,
        remark=remark,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysOcrTool:
    row = await get_tool(
        session,
        workspace_id=workspace_id,
        tool_id=tool_id,
    )
    for key, value in patch.items():
        setattr(row, key, value)
    row.update_at = _utc_now()
    await session.commit()
    await session.refresh(row)
    return row


async def delete_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
) -> None:
    row = await get_tool(
        session,
        workspace_id=workspace_id,
        tool_id=tool_id,
    )
    await session.delete(row)
    await session.commit()
