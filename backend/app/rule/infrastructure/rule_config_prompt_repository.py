"""Async repository helpers for ``RuleConfigPrompt`` joined with ``SysModel``."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.rule.domain.db.models import RuleConfigPrompt
from app.rule.domain.scope_triple import scope_triple_filter_conditions, scope_triple_match_conditions
from app.sys.model_provider.domain.db.models import SysModel


async def count_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    engineering_code: str | None = None,
    subject_code: str | None = None,
    document_type: str | None = None,
) -> int:
    conds = scope_triple_filter_conditions(
        RuleConfigPrompt,
        workspace_id,
        engineering_code,
        subject_code,
        document_type,
    )
    result = await session.execute(
        select(func.count()).select_from(RuleConfigPrompt).where(and_(*conds))
    )
    return int(result.scalar_one() or 0)


async def list_page_joined(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
    engineering_code: str | None = None,
    subject_code: str | None = None,
    document_type: str | None = None,
) -> Sequence[tuple[RuleConfigPrompt, str, str]]:
    m = aliased(SysModel)
    conds = scope_triple_filter_conditions(
        RuleConfigPrompt,
        workspace_id,
        engineering_code,
        subject_code,
        document_type,
    )
    result = await session.execute(
        select(RuleConfigPrompt, m.provider_name, m.model_name)
        .join(m, RuleConfigPrompt.model_id == m.id)
        .where(and_(*conds))
        .order_by(nulls_last(RuleConfigPrompt.create_at.desc()))
        .limit(limit)
        .offset(offset)
    )
    return result.all()


async def get_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    config_prompt_id: uuid.UUID,
) -> tuple[RuleConfigPrompt, str, str] | None:
    m = aliased(SysModel)
    result = await session.execute(
        select(RuleConfigPrompt, m.provider_name, m.model_name)
        .join(m, RuleConfigPrompt.model_id == m.id)
        .where(
            RuleConfigPrompt.id == config_prompt_id,
            RuleConfigPrompt.workspace_id == workspace_id,
        )
        .limit(1)
    )
    row = result.first()
    return row


async def find_by_scope_exact(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
    exclude_id: uuid.UUID | None = None,
) -> RuleConfigPrompt | None:
    conds = scope_triple_match_conditions(
        RuleConfigPrompt,
        workspace_id,
        engineering_code,
        subject_code,
        document_type,
    )
    if exclude_id is not None:
        conds.append(RuleConfigPrompt.id != exclude_id)
    result = await session.execute(select(RuleConfigPrompt).where(and_(*conds)).limit(1))
    return result.scalar_one_or_none()


async def try_resolve(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
) -> RuleConfigPrompt | None:
    candidates: list[tuple[str | None, str | None, str | None]] = [
        (engineering_code, subject_code, document_type),
        (engineering_code, subject_code, None),
        (engineering_code, None, None),
        (None, None, None),
    ]
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for triple in candidates:
        if triple in seen:
            continue
        seen.add(triple)
        e, s, d = triple
        row = await find_by_scope_exact(
            session,
            workspace_id=workspace_id,
            engineering_code=e,
            subject_code=s,
            document_type=d,
        )
        if row is not None:
            return row
    return None


async def add(session: AsyncSession, row: RuleConfigPrompt) -> RuleConfigPrompt:
    session.add(row)
    await session.flush()
    return row


async def delete_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    config_prompt_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        select(RuleConfigPrompt).where(
            RuleConfigPrompt.id == config_prompt_id,
            RuleConfigPrompt.workspace_id == workspace_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    return True
