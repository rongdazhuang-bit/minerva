from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.rule.domain.db.models import RuleBase
from app.sys.rule.infrastructure import repository as repo


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
