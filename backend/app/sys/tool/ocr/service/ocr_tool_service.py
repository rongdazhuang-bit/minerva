"""Use cases for OCR tool rows scoped per workspace."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.tool.ocr.domain.db.models import SysOcrTool
from app.sys.tool.ocr.infrastructure import repository as repo


def normalize_ocr_config_from_db(raw: Any) -> dict | None:
    """Map JSON column values to ``dict`` or ``None`` for API responses.

    Some async PG drivers return JSON/JSONB as a string; normalize so
    ``OcrToolDetailOut`` always receives a dict or None.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return None if not raw else raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            parsed: Any = json.loads(s)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return None if not parsed else parsed
    return None


def _coerce_ocr_config_payload(raw: Any) -> dict | None:
    """Normalize API payloads and turn empty configs into None before persist."""
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            raw = json.loads(s)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    if not raw:
        return None
    return raw


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
    ocr_type: str | None,
    ocr_config: Any,
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
        ocr_type=ocr_type,
        ocr_config=_coerce_ocr_config_payload(ocr_config),
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
        if key == "ocr_config":
            value = _coerce_ocr_config_payload(value)
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
