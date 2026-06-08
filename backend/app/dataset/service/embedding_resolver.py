"""Embedding model resolution from sys_models."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.llm.service.model_resolver import _normalize_tag_set, resolve_model
from app.sys.model_provider.domain.constants import MODEL_TAG_EMBEDDINGS
from app.sys.model_provider.domain.db.models import SysModel


async def resolve_embedding_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    provider_name: str,
    model_name: str,
):
    """Resolve an enabled Embedding-tagged sys_models row for the workspace."""

    stmt = select(SysModel).where(
        SysModel.workspace_id == workspace_id,
        SysModel.provider_name == provider_name.strip(),
        SysModel.model_name == model_name.strip(),
        SysModel.enabled.is_(True),
    )
    row = await session.scalar(stmt)
    if row is None:
        raise AppError("dataset.embedding_model_not_found", "Embedding 模型不存在或未启用。", 422)
    if MODEL_TAG_EMBEDDINGS not in _normalize_tag_set(row.tags):
        raise AppError("dataset.embedding_model_invalid", "所选模型不是 Embedding 模型。", 422)
    return await resolve_model(
        session,
        workspace_id=workspace_id,
        model_id=row.id,
        allowed_tags=frozenset({MODEL_TAG_EMBEDDINGS}),
    )
