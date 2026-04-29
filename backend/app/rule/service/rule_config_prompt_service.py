"""Use cases for Rule Config Prompt rows joined against catalog models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.rule.domain.db.models import RuleConfigPrompt
from app.rule.domain.scope_triple import (
    normalize_patch_scope_fields,
    normalize_scope_triple,
)
from app.rule.infrastructure import rule_config_prompt_repository as rcp_repo
from app.sys.model_provider.service import model_provider_service as model_svc


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def resolve_rule_config_prompt(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
) -> RuleConfigPrompt:
    e, s, d = normalize_scope_triple(engineering_code, subject_code, document_type)
    row = await rcp_repo.try_resolve(
        session,
        workspace_id=workspace_id,
        engineering_code=e,
        subject_code=s,
        document_type=d,
    )
    if row is None:
        raise AppError(
            "rule_config_prompt.not_found",
            "No prompt configuration matches this context",
            422,
        )
    return row


async def _ensure_model_in_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
) -> None:
    await model_svc.get_model(session, workspace_id=workspace_id, model_id=model_id)


async def _conflict_if_duplicate_scope(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
    exclude_id: uuid.UUID | None,
) -> None:
    existing = await rcp_repo.find_by_scope_exact(
        session,
        workspace_id=workspace_id,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
        exclude_id=exclude_id,
    )
    if existing is not None:
        raise AppError(
            "rule_config_prompt.conflict",
            "A prompt configuration already exists for this workspace and scope triple",
            409,
        )


async def list_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    engineering_code: str | None = None,
    subject_code: str | None = None,
    document_type: str | None = None,
) -> tuple[list[tuple[RuleConfigPrompt, str, str]], int]:
    engineering_code, subject_code, document_type = normalize_scope_triple(
        engineering_code, subject_code, document_type
    )
    total = await rcp_repo.count_for_workspace(
        session,
        workspace_id=workspace_id,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
    )
    offset = (page - 1) * page_size
    rows = await rcp_repo.list_page_joined(
        session,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
    )
    return list(rows), total


async def get_one(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    config_prompt_id: uuid.UUID,
) -> tuple[RuleConfigPrompt, str, str]:
    row = await rcp_repo.get_for_workspace(
        session, workspace_id=workspace_id, config_prompt_id=config_prompt_id
    )
    if row is None:
        raise AppError("rule_config_prompt.not_found", "Prompt configuration not found", 404)
    return row


async def create(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
    sys_prompt: str | None,
    user_prompt: str | None,
    chat_memory: str | None,
) -> tuple[RuleConfigPrompt, str, str]:
    engineering_code, subject_code, document_type = normalize_scope_triple(
        engineering_code, subject_code, document_type
    )
    await _ensure_model_in_workspace(
        session, workspace_id=workspace_id, model_id=model_id
    )
    await _conflict_if_duplicate_scope(
        session,
        workspace_id=workspace_id,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
        exclude_id=None,
    )
    now = _utc_now()
    row = RuleConfigPrompt(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        model_id=model_id,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
        sys_prompt=sys_prompt,
        user_prompt=user_prompt,
        chat_memory=chat_memory,
        create_at=now,
        update_at=now,
    )
    await rcp_repo.add(session, row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(
            "rule_config_prompt.conflict",
            "A prompt configuration already exists for this workspace and scope triple",
            409,
        ) from None
    await session.refresh(row)
    m = await model_svc.get_model(session, workspace_id=workspace_id, model_id=model_id)
    return row, m.provider_name, m.model_name


async def update(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    config_prompt_id: uuid.UUID,
    patch: dict[str, Any],
) -> tuple[RuleConfigPrompt, str, str]:
    patch = normalize_patch_scope_fields(patch)
    row_t = await rcp_repo.get_for_workspace(
        session, workspace_id=workspace_id, config_prompt_id=config_prompt_id
    )
    if row_t is None:
        raise AppError("rule_config_prompt.not_found", "Prompt configuration not found", 404)
    row, _, _ = row_t

    next_e = (
        patch["engineering_code"] if "engineering_code" in patch else row.engineering_code
    )
    next_s = patch["subject_code"] if "subject_code" in patch else row.subject_code
    next_d = patch["document_type"] if "document_type" in patch else row.document_type
    next_e, next_s, next_d = normalize_scope_triple(next_e, next_s, next_d)

    scope_keys = {"engineering_code", "subject_code", "document_type"}
    if scope_keys & patch.keys():
        await _conflict_if_duplicate_scope(
            session,
            workspace_id=workspace_id,
            engineering_code=next_e,
            subject_code=next_s,
            document_type=next_d,
            exclude_id=config_prompt_id,
        )

    if "model_id" in patch:
        mid = patch["model_id"]
        if isinstance(mid, str):
            mid = uuid.UUID(mid)
        elif not isinstance(mid, uuid.UUID):
            mid = uuid.UUID(str(mid))
        await _ensure_model_in_workspace(
            session, workspace_id=workspace_id, model_id=mid
        )
        row.model_id = mid

    if scope_keys & patch.keys():
        row.engineering_code = next_e
        row.subject_code = next_s
        row.document_type = next_d
    for k in ("sys_prompt", "user_prompt", "chat_memory"):
        if k in patch:
            setattr(row, k, patch[k])

    row.update_at = _utc_now()
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(
            "rule_config_prompt.conflict",
            "A prompt configuration already exists for this workspace and scope triple",
            409,
        ) from None
    await session.refresh(row)
    m = await model_svc.get_model(
        session, workspace_id=workspace_id, model_id=row.model_id
    )
    return row, m.provider_name, m.model_name


async def delete(
    session: AsyncSession, *, workspace_id: uuid.UUID, config_prompt_id: uuid.UUID
) -> None:
    ok = await rcp_repo.delete_for_workspace(
        session, workspace_id=workspace_id, config_prompt_id=config_prompt_id
    )
    if not ok:
        raise AppError("rule_config_prompt.not_found", "Prompt configuration not found", 404)
    await session.commit()
