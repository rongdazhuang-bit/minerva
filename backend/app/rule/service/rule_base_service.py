"""Application services orchestrating Rule Base persistence, repositories, and AI polish."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.domain.models import ChatMessage
from app.llm.service.llm_service import llm_service
from app.exceptions import AppError
from app.rule.domain.db.models import RuleBase
from app.rule.domain.scope_triple import (
    normalize_patch_scope_fields,
    normalize_scope_triple,
)
from app.rule.infrastructure import repository as repo
from app.rule.infrastructure import rule_config_prompt_repository as rcp_repo
from app.sys.model_provider.service import model_provider_service as model_svc


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def get_rule_base_overview_stats(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
) -> tuple[int, list[str], list[str], list[str]]:
    return await repo.overview_stats_for_workspace(session, workspace_id=workspace_id)


async def get_rule_base(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> RuleBase:
    row = await repo.get_for_workspace(
        session, workspace_id=workspace_id, rule_id=rule_id
    )
    if row is None:
        raise AppError("rule_base.not_found", "Rule not found", 404)
    return row


async def list_rule_base_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    status: str | None = None,
    engineering_code: str | None = None,
    subject_code: str | None = None,
    document_type: str | None = None,
) -> tuple[list[RuleBase], int]:
    engineering_code, subject_code, document_type = normalize_scope_triple(
        engineering_code, subject_code, document_type
    )
    total = await repo.count_for_workspace(
        session,
        workspace_id=workspace_id,
        status=status,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
    )
    offset = (page - 1) * page_size
    rows = await repo.list_for_workspace_page(
        session,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
        status=status,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
    )
    return list(rows), total


async def create_rule_base(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    sequence_number: int,
    engineering_code: str | None,
    subject_code: str | None,
    serial_number: str | None,
    document_type: str | None,
    review_section: str,
    review_object: str,
    review_rules: str,
    review_rules_ai: str | None,
    review_result: str,
    status: str,
) -> RuleBase:
    engineering_code, subject_code, document_type = normalize_scope_triple(
        engineering_code, subject_code, document_type
    )
    now = _utc_now()
    row = RuleBase(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        sequence_number=sequence_number,
        engineering_code=engineering_code,
        subject_code=subject_code,
        serial_number=serial_number,
        document_type=document_type,
        review_section=review_section,
        review_object=review_object,
        review_rules=review_rules,
        review_rules_ai=review_rules_ai,
        review_result=review_result,
        status=status,
        create_at=now,
        update_at=now,
    )
    out = await repo.add(session, row)
    await session.commit()
    return out


async def update_rule_base(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
    patch: dict[str, Any],
) -> RuleBase:
    patch = normalize_patch_scope_fields(patch)
    row = await repo.get_for_workspace(
        session, workspace_id=workspace_id, rule_id=rule_id
    )
    if row is None:
        raise AppError("rule_base.not_found", "Rule not found", 404)
    for k, v in patch.items():
        setattr(row, k, v)
    row.update_at = _utc_now()
    await session.commit()
    await session.refresh(row)
    return row


async def delete_rule_base(
    session: AsyncSession, *, workspace_id: uuid.UUID, rule_id: uuid.UUID
) -> None:
    ok = await repo.delete_for_workspace(
        session, workspace_id=workspace_id, rule_id=rule_id
    )
    if not ok:
        raise AppError("rule_base.not_found", "Rule not found", 404)
    await session.commit()



async def polish_review_rules(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
    review_rules: str,
) -> str:
    e, s, d = normalize_scope_triple(engineering_code, subject_code, document_type)
    cfg = await rcp_repo.try_resolve(
        session,
        workspace_id=workspace_id,
        engineering_code=e,
        subject_code=s,
        document_type=d,
    )
    if cfg is None:
        raise AppError(
            "rule_config_prompt.polish_not_configured",
            "未配置相关提示词，请先配置",
            422,
        )

    model_row = await model_svc.get_model(
        session, workspace_id=workspace_id, model_id=cfg.model_id
    )
    if model_row.enabled is False:
        raise AppError(
            "model_provider.disabled",
            "所选模型已禁用，无法在润色流程中使用",
            422,
        )

    system_parts: list[str] = []
    if (cfg.sys_prompt or "").strip():
        system_parts.append(cfg.sys_prompt.strip())
    if (cfg.chat_memory or "").strip():
        system_parts.append(f"对话记忆（上下文）：\n{cfg.chat_memory.strip()}")
    system_prompt = "\n\n".join(system_parts).strip()

    msgs: list[ChatMessage] = []
    rules = review_rules.strip()
    if (cfg.user_prompt or "").strip():
        msgs.append(ChatMessage(role="user", content=cfg.user_prompt.strip()))
    msgs.append(ChatMessage(role="user", content=rules))

    mt = model_row.max_tokens_to_sample
    max_tokens = int(mt) if mt is not None else None

    result = await llm_service.complete_chat(
        session,
        workspace_id=workspace_id,
        model_id=cfg.model_id,
        system_prompt=system_prompt or None,
        user_prompt=None,
        messages=msgs,
        temperature=None,
        max_tokens=max_tokens,
        allowed_tags=frozenset({"TEXT"}),
        excluded_tags=frozenset({"TRANSLATE"}),
    )
    text = result.assistant_text()
    if not result.choices:
        raise AppError("ai.polish.empty_choices", "模型未返回内容", 502)
    if not text:
        raise AppError("ai.polish.empty_content", "模型返回内容为空", 502)
    return text
