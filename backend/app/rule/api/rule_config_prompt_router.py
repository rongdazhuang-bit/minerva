"""Workspace CRUD endpoints for Rule Config prompts tied to catalog models."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.core.domain.identity.models import User
from app.pagination import DEFAULT_PAGE_SIZE
from app.rule.api.schemas import (
    RuleConfigPromptCreateIn,
    RuleConfigPromptListItemOut,
    RuleConfigPromptListPageOut,
    RuleConfigPromptPatchIn,
)
from app.rule.domain.db.models import RuleConfigPrompt
from app.rule.service import rule_config_prompt_service as rcp_svc

router = APIRouter(
    prefix="/workspaces/{workspace_id}/rule-config/config-prompts",
    tags=["rule-config-prompts"],
)


def _to_item(
    row: RuleConfigPrompt, provider_name: str, model_name: str
) -> RuleConfigPromptListItemOut:
    """Map ORM row plus joined catalog labels into outbound schema."""

    return RuleConfigPromptListItemOut(
        id=row.id,
        workspace_id=row.workspace_id,
        model_id=row.model_id,
        provider_name=provider_name,
        model_name=model_name,
        engineering_code=row.engineering_code,
        subject_code=row.subject_code,
        document_type=row.document_type,
        sys_prompt=row.sys_prompt,
        user_prompt=row.user_prompt,
        chat_memory=row.chat_memory,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _optional_longtext(s: str | None) -> str | None:
    """Normalize nullable prompt blobs."""

    if s is None:
        return None
    t = s.strip()
    return t if t else None


def _patch_from_body(body: RuleConfigPromptPatchIn) -> dict[str, Any]:
    """Convert pydantic patch payload into SQL assignment mapping."""

    data = body.model_dump(exclude_unset=True)
    out: dict[str, Any] = dict(data)
    for k in ("sys_prompt", "user_prompt", "chat_memory"):
        if k in out and isinstance(out[k], str):
            out[k] = _optional_longtext(out[k])
    return out


@router.get("", response_model=RuleConfigPromptListPageOut)
async def list_rule_config_prompts(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    engineering_code: str | None = Query(default=None),
    subject_code: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleConfigPromptListPageOut:
    """Paginate prompt rows filtered by optional facet triple."""

    rows, total = await rcp_svc.list_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
    )
    return RuleConfigPromptListPageOut(
        items=[_to_item(r, pn, mn) for r, pn, mn in rows],
        total=total,
    )


@router.post(
    "",
    response_model=RuleConfigPromptListItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_config_prompt(
    workspace_id: uuid.UUID,
    body: RuleConfigPromptCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleConfigPromptListItemOut:
    """Persist prompt triple referencing configured catalog model."""

    row, pn, mn = await rcp_svc.create(
        session,
        workspace_id=workspace_id,
        model_id=body.model_id,
        engineering_code=body.engineering_code,
        subject_code=body.subject_code,
        document_type=body.document_type,
        sys_prompt=_optional_longtext(body.sys_prompt),
        user_prompt=_optional_longtext(body.user_prompt),
        chat_memory=_optional_longtext(body.chat_memory),
    )
    return _to_item(row, pn, mn)


@router.get("/{config_prompt_id}", response_model=RuleConfigPromptListItemOut)
async def get_rule_config_prompt(
    workspace_id: uuid.UUID,
    config_prompt_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleConfigPromptListItemOut:
    """Fetch prompt configuration row by id."""

    row, pn, mn = await rcp_svc.get_one(
        session, workspace_id=workspace_id, config_prompt_id=config_prompt_id
    )
    return _to_item(row, pn, mn)


@router.patch("/{config_prompt_id}", response_model=RuleConfigPromptListItemOut)
async def patch_rule_config_prompt(
    workspace_id: uuid.UUID,
    config_prompt_id: uuid.UUID,
    body: RuleConfigPromptPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleConfigPromptListItemOut:
    """Partially update prompts or short-circuit no-op fetch."""

    patch = _patch_from_body(body)
    if not patch:
        row, pn, mn = await rcp_svc.get_one(
            session, workspace_id=workspace_id, config_prompt_id=config_prompt_id
        )
        return _to_item(row, pn, mn)
    row, pn, mn = await rcp_svc.update(
        session,
        workspace_id=workspace_id,
        config_prompt_id=config_prompt_id,
        patch=patch,
    )
    return _to_item(row, pn, mn)


@router.delete(
    "/{config_prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_rule_config_prompt(
    workspace_id: uuid.UUID,
    config_prompt_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Delete prompt configuration."""

    await rcp_svc.delete(
        session, workspace_id=workspace_id, config_prompt_id=config_prompt_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
