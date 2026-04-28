from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.rule.domain.db.models import RuleBase


def _list_filters(
    workspace_id: uuid.UUID,
    *,
    status: str | None,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
) -> list:
    conds: list = [RuleBase.workspace_id == workspace_id]
    if status is not None:
        conds.append(RuleBase.status == status)
    if engineering_code is not None:
        conds.append(RuleBase.engineering_code == engineering_code)
    if subject_code is not None:
        conds.append(RuleBase.subject_code == subject_code)
    if document_type is not None:
        conds.append(RuleBase.document_type == document_type)
    return conds


async def count_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    status: str | None = None,
    engineering_code: str | None = None,
    subject_code: str | None = None,
    document_type: str | None = None,
) -> int:
    conds = _list_filters(
        workspace_id,
        status=status,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
    )
    result = await session.execute(
        select(func.count()).select_from(RuleBase).where(and_(*conds))
    )
    return int(result.scalar_one() or 0)


async def list_for_workspace_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
    status: str | None = None,
    engineering_code: str | None = None,
    subject_code: str | None = None,
    document_type: str | None = None,
) -> Sequence[RuleBase]:
    conds = _list_filters(
        workspace_id,
        status=status,
        engineering_code=engineering_code,
        subject_code=subject_code,
        document_type=document_type,
    )
    result = await session.execute(
        select(RuleBase)
        .where(and_(*conds))
        .order_by(
            RuleBase.sequence_number.asc(),
            nulls_last(RuleBase.create_at.desc()),
        )
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> RuleBase | None:
    result = await session.execute(
        select(RuleBase).where(
            RuleBase.id == rule_id,
            RuleBase.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def add(session: AsyncSession, row: RuleBase) -> RuleBase:
    session.add(row)
    await session.flush()
    return row


async def delete_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> bool:
    row = await get_for_workspace(session, workspace_id=workspace_id, rule_id=rule_id)
    if row is None:
        return False
    await session.delete(row)
    return True
