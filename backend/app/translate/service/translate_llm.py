"""Call workspace translate models for one paragraph via ``app.llm``."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.llm.domain.models import ChatMessage
from app.llm.service.llm_service import llm_service
from app.llm.service.model_resolver import resolve_model
from app.sys.dict.service import dictionary_service as dict_service
from app.sys.model_provider.infrastructure import repository as model_repo

TRANSLATE_MODEL_TYPES = frozenset({"translate"})


async def _assert_translate_dict(session: AsyncSession, *, workspace_id: uuid.UUID) -> None:
    """Ensure workspace MODEL_TYPE dictionary includes translate."""

    allowed_types = await dict_service.list_items_by_dict_code(
        session, workspace_id=workspace_id, dict_code="MODEL_TYPE"
    )
    codes = {i.code.strip() for i in allowed_types if (i.code or "").strip()}
    if "translate" not in codes:
        raise AppError(
            "translate.model_type_dict_missing",
            "字典 MODEL_TYPE 缺少 translate 项。",
            422,
        )


async def _assert_translate_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
) -> None:
    """Ensure MODEL_TYPE dict and workspace model are valid for translate jobs."""

    await _assert_translate_dict(session, workspace_id=workspace_id)
    await resolve_model(
        session,
        workspace_id=workspace_id,
        model_id=model_id,
        allowed_types=TRANSLATE_MODEL_TYPES,
    )


async def translate_segment(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    source_lang: str,
    target_lang: str,
    source_text: str,
) -> str:
    """Translate one paragraph; returns target-language text only."""

    await _assert_translate_dict(session, workspace_id=workspace_id)
    row = await model_repo.get_for_workspace(
        session, workspace_id=workspace_id, model_id=model_id
    )
    if row is None:
        raise AppError("translate.model_not_found", "翻译模型不存在或不属于当前工作区。", 404)

    system_prompt = (
        f"You are a professional translator. Translate from {source_lang} to {target_lang}. "
        "Output only the translated text without explanations or quotes."
    )
    configured_max = row.max_tokens_to_sample
    estimated_out = min(32767, max(512, int(len(source_text) * 1.6) + 128))
    max_tokens = min(32767, max(configured_max or 0, estimated_out))

    result = await llm_service.complete_chat(
        session,
        workspace_id=workspace_id,
        model_id=model_id,
        system_prompt=system_prompt,
        user_prompt=source_text,
        messages=[ChatMessage(role="user", content=source_text)],
        temperature=0.2,
        max_tokens=max_tokens,
        allowed_types=TRANSLATE_MODEL_TYPES,
    )
    text = result.assistant_text()
    if not text:
        raise AppError("translate.empty_response", "模型返回空译文。", 502)
    return text
