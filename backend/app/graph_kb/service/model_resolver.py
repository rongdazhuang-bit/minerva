"""Resolve Chat and Embedding models for GraphKB create / index flows."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.service.model_resolver import _normalize_tag_set, resolve_model
from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT, MODEL_TAG_EMBEDDINGS
from app.sys.model_provider.domain.db.models import SysModel


async def _load_enabled_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    provider_name: str | None,
    model_name: str | None,
) -> SysModel | None:
    """Load an enabled ``sys_models`` row by provider + name within a workspace."""

    if provider_name is None or model_name is None:
        return None
    provider = provider_name.strip()
    name = model_name.strip()
    if not provider or not name:
        return None
    stmt = select(SysModel).where(
        SysModel.workspace_id == workspace_id,
        SysModel.provider_name == provider,
        SysModel.model_name == name,
        SysModel.enabled.is_(True),
    )
    return await session.scalar(stmt)


async def resolve_graph_models(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    llm_provider: str | None,
    llm_name: str | None,
    emb_provider: str | None,
    emb_name: str | None,
) -> tuple[ResolvedModel, ResolvedModel]:
    """Resolve Chat and Embedding bindings; raise 400 when either is missing/invalid.

    Used before creating a graph job and when enqueueing index/reindex.
    """

    llm_row = await _load_enabled_model(
        session,
        workspace_id=workspace_id,
        provider_name=llm_provider,
        model_name=llm_name,
    )
    if llm_row is None or MODEL_TAG_CHAT not in _normalize_tag_set(llm_row.tags):
        raise AppError(
            "graph_kb.llm_model_not_found",
            "Chat 模型不存在、未启用或标签不匹配。",
            400,
        )

    emb_row = await _load_enabled_model(
        session,
        workspace_id=workspace_id,
        provider_name=emb_provider,
        model_name=emb_name,
    )
    if emb_row is None or MODEL_TAG_EMBEDDINGS not in _normalize_tag_set(emb_row.tags):
        raise AppError(
            "graph_kb.embedding_model_not_found",
            "Embedding 模型不存在、未启用或标签不匹配。",
            400,
        )

    llm = await resolve_model(
        session,
        workspace_id=workspace_id,
        model_id=llm_row.id,
        allowed_tags=frozenset({MODEL_TAG_CHAT}),
    )
    emb = await resolve_model(
        session,
        workspace_id=workspace_id,
        model_id=emb_row.id,
        allowed_tags=frozenset({MODEL_TAG_EMBEDDINGS}),
    )
    return llm, emb
