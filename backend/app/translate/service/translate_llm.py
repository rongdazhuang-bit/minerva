"""Call workspace translate models for one paragraph via ``app.llm``."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.llm.domain.models import ChatMessage
from app.llm.service.chat_service import chat_service
from app.sys.dict.service import dictionary_service as dict_service
from app.sys.model_provider.infrastructure import repository as model_repo


def _openai_completion_text(payload: dict[str, Any]) -> str:
    """Extract assistant text from an OpenAI-style chat completion payload."""

    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    return (content or "").strip() if isinstance(content, str) else ""


async def _assert_translate_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
) -> Any:
    """Load ``sys_models`` row and ensure it is an enabled translate-type model."""

    row = await model_repo.get_for_workspace(
        session, workspace_id=workspace_id, model_id=model_id
    )
    if row is None:
        raise AppError("translate.model_not_found", "翻译模型不存在或不属于当前工作区。", 404)
    if not row.enabled:
        raise AppError("translate.model_disabled", "翻译模型未启用。", 422)
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
    if row.model_type.strip() != "translate":
        raise AppError("translate.model_type_invalid", "请选择 model_type 为 translate 的模型。", 422)
    endpoint = (row.endpoint_url or "").strip()
    api_key = (row.api_key or "").strip()
    if not endpoint or not api_key:
        raise AppError("translate.model_misconfigured", "模型缺少 endpoint_url 或 api_key。", 422)
    return row


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

    row = await _assert_translate_model(
        session, workspace_id=workspace_id, model_id=model_id
    )
    system_prompt = (
        f"You are a professional translator. Translate from {source_lang} to {target_lang}. "
        "Output only the translated text without explanations or quotes."
    )
    endpoint = (row.endpoint_url or "").strip()
    api_key = (row.api_key or "").strip()
    configured_max = row.max_tokens_to_sample
    # Avoid truncated translations when the model max output is smaller than the source.
    estimated_out = min(32767, max(512, int(len(source_text) * 1.6) + 128))
    max_tokens = min(32767, max(configured_max or 0, estimated_out))

    payload = await chat_service.complete(
        base_url=endpoint.rstrip("/"),
        api_key=api_key,
        model=row.model_name.strip(),
        system_prompt=system_prompt,
        user_prompt=source_text,
        messages=[ChatMessage(role="user", content=source_text)],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    text = _openai_completion_text(payload)
    if not text:
        raise AppError("translate.empty_response", "模型返回空译文。", 502)
    return text
