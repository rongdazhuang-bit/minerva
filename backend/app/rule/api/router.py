from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.domain.identity.models import User
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.rule.api.schemas import (
    RuleBaseCreateIn,
    RuleBaseListItemOut,
    RuleBaseListPageOut,
    RuleBasePatchIn,
    RuleBasePolishReviewRulesIn,
    RuleBasePolishReviewRulesOut,
)
from app.sys.rule.domain.db.models import RuleBase
from app.sys.rule.service import rule_base_service as svc

router = APIRouter(prefix="/workspaces/{workspace_id}/rule-base", tags=["rule-base"])


def _to_out(row: RuleBase) -> RuleBaseListItemOut:
    return RuleBaseListItemOut(
        id=row.id,
        workspace_id=row.workspace_id,
        sequence_number=row.sequence_number,
        engineering_code=row.engineering_code,
        subject_code=row.subject_code,
        serial_number=row.serial_number,
        document_type=row.document_type,
        review_section=row.review_section,
        review_object=row.review_object,
        review_rules=row.review_rules,
        review_rules_ai=row.review_rules_ai,
        review_result=row.review_result,
        status=row.status,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _strip_opt(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return t if t else None


def _optional_text(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return t if t else None


def _patch_from_body(body: RuleBasePatchIn) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in (
            "engineering_code",
            "subject_code",
            "serial_number",
            "document_type",
        ) and isinstance(
            value, str
        ):
            out[key] = _strip_opt(value)
        elif key in ("review_section", "review_object") and isinstance(value, str):
            out[key] = value.strip()
        elif key in ("review_rules", "review_result") and isinstance(value, str):
            out[key] = value.strip()
        elif key == "review_rules_ai":
            if isinstance(value, str):
                t = value.strip()
                out[key] = t if t else None
            else:
                out[key] = value
        else:
            out[key] = value
    return out


@router.get("", response_model=RuleBaseListPageOut)
async def list_rule_base(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    status: str | None = Query(default=None),
    engineering_code: str | None = Query(default=None),
    subject_code: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleBaseListPageOut:
    rows, total = await svc.list_rule_base_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=_strip_opt(status),
        engineering_code=_strip_opt(engineering_code),
        subject_code=_strip_opt(subject_code),
        document_type=_strip_opt(document_type),
    )
    return RuleBaseListPageOut(
        items=[_to_out(r) for r in rows],
        total=total,
    )


@router.post(
    "",
    response_model=RuleBaseListItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_base(
    workspace_id: uuid.UUID,
    body: RuleBaseCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleBaseListItemOut:
    row = await svc.create_rule_base(
        session,
        workspace_id=workspace_id,
        sequence_number=body.sequence_number,
        engineering_code=_strip_opt(body.engineering_code),
        subject_code=_strip_opt(body.subject_code),
        serial_number=_strip_opt(body.serial_number),
        document_type=_strip_opt(body.document_type),
        review_section=body.review_section.strip(),
        review_object=body.review_object.strip(),
        review_rules=body.review_rules.strip(),
        review_rules_ai=_optional_text(body.review_rules_ai),
        review_result=body.review_result.strip(),
        status=body.status,
    )
    return _to_out(row)


@router.post(
    "/polish-review-rules",
    response_model=RuleBasePolishReviewRulesOut,
)
async def polish_review_rules(
    workspace_id: uuid.UUID,
    body: RuleBasePolishReviewRulesIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> RuleBasePolishReviewRulesOut:
    # Placeholder until a real LLM/service integration exists.
    src = body.review_rules.strip()
    polished = f"[AI polish placeholder]\n{src}"
    return RuleBasePolishReviewRulesOut(review_rules_ai=polished)


@router.patch("/{rule_id}", response_model=RuleBaseListItemOut)
async def patch_rule_base(
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: RuleBasePatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleBaseListItemOut:
    patch = _patch_from_body(body)
    if not patch:
        row = await svc.get_rule_base(
            session, workspace_id=workspace_id, rule_id=rule_id
        )
        return _to_out(row)
    row = await svc.update_rule_base(
        session,
        workspace_id=workspace_id,
        rule_id=rule_id,
        patch=patch,
    )
    return _to_out(row)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_rule_base(
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await svc.delete_rule_base(session, workspace_id=workspace_id, rule_id=rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
