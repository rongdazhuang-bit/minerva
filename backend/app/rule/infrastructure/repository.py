from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rule.domain.db.models import RuleBase
from app.rule.domain.scope_triple import scope_triple_filter_conditions


def _list_filters(
    workspace_id: uuid.UUID,
    *,
    status: str | None,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
) -> list:
    conds: list = scope_triple_filter_conditions(
        RuleBase,
        workspace_id,
        engineering_code,
        subject_code,
        document_type,
    )
    if status is not None:
        conds.append(RuleBase.status == status)
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


async def overview_stats_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
) -> tuple[int, list[str], list[str], list[str]]:
    """规则总数；三列 trim 后非空的 distinct code，按 trim 值升序。"""
    base_ws = RuleBase.workspace_id == workspace_id
    rc = await session.execute(
        select(func.count()).select_from(RuleBase).where(base_ws)
    )
    rule_count = int(rc.scalar_one() or 0)

    async def _distinct_trimmed(column) -> list[str]:
        stmt = (
            select(func.trim(column))
            .where(
                base_ws,
                column.isnot(None),
                func.trim(column) != "",
            )
            .distinct()
            .order_by(func.trim(column))
        )
        rows = await session.execute(stmt)
        return [row[0] for row in rows.all()]

    engineering_codes = await _distinct_trimmed(RuleBase.engineering_code)
    subject_codes = await _distinct_trimmed(RuleBase.subject_code)
    document_type_codes = await _distinct_trimmed(RuleBase.document_type)
    return rule_count, engineering_codes, subject_codes, document_type_codes
