"""Lightweight queries listing catalog ``SysModel`` rows."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT
from app.sys.model_provider.domain.db.models import SysModel


def agent_conversation_models_select(*, workspace_id: uuid.UUID):
    """Build SELECT for workspace agent-usable models (caller executes)."""

    endpoint_ok = (SysModel.endpoint_url.isnot(None)) & (
        func.btrim(SysModel.endpoint_url) != ""
    )
    api_key_ok = (SysModel.api_key.isnot(None)) & (func.btrim(SysModel.api_key) != "")
    return (
        select(SysModel)
        .where(
            SysModel.workspace_id == workspace_id,
            SysModel.enabled.is_(True),
            SysModel.tags.contains([MODEL_TAG_CHAT]),
            endpoint_ok,
            api_key_ok,
        )
        .order_by(
            SysModel.provider_name.asc(),
            SysModel.model_name.asc(),
            SysModel.id.asc(),
        )
    )


async def list_agent_conversation_models(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysModel]:
    """Return models usable for agent conversation (SQL-filtered)."""

    result = await session.execute(
        agent_conversation_models_select(workspace_id=workspace_id)
    )
    return result.scalars().all()


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
