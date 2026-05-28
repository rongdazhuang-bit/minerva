"""Resolve workspace model_id into upstream credentials."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import normalize_endpoint_url
from app.sys.model_provider.infrastructure import repository as model_repo


async def resolve_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    allowed_types: frozenset[str],
) -> ResolvedModel:
    """Load ``sys_models`` row and validate type, enabled state, and credentials."""

    row = await model_repo.get_for_workspace(
        session, workspace_id=workspace_id, model_id=model_id
    )
    if row is None:
        raise AppError("ai.model_not_found", "模型不存在或不属于当前工作区。", 404)
    if not row.enabled:
        raise AppError("ai.model_disabled", "模型未启用。", 422)
    model_type = (row.model_type or "").strip()
    if model_type not in allowed_types:
        raise AppError(
            "ai.model_type_mismatch",
            f"模型类型 {model_type!r} 不支持当前调用。",
            422,
        )
    endpoint = normalize_endpoint_url((row.endpoint_url or "").strip())
    api_key = (row.api_key or "").strip()
    if not api_key and (row.auth_type or "").strip().upper() == "NONE":
        api_key = "-"
    if not endpoint or not api_key:
        raise AppError("ai.model_misconfigured", "模型缺少 endpoint_url 或 api_key。", 422)
    return ResolvedModel(
        model_id=row.id,
        model_name=row.model_name.strip(),
        model_type=model_type,
        endpoint_url=endpoint,
        api_key=api_key,
    )
