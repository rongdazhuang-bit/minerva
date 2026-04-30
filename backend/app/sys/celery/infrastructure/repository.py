"""Persistence queries for workspace-scoped ``SysCelery`` jobs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.celery.domain.db.models import SysCelery


def _job_order():
    """Return default ordering for job list endpoints."""

    return (
        SysCelery.create_at.desc().nulls_last(),
        SysCelery.id.desc(),
    )


async def count_for_workspace(session: AsyncSession, *, workspace_id: uuid.UUID) -> int:
    """Count total jobs under one workspace."""

    result = await session.execute(
        select(func.count()).select_from(SysCelery).where(
            SysCelery.workspace_id == workspace_id
        )
    )
    return int(result.scalar_one() or 0)


async def list_for_workspace_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
) -> Sequence[SysCelery]:
    """List one page of jobs under workspace scope."""

    result = await session.execute(
        select(SysCelery)
        .where(SysCelery.workspace_id == workspace_id)
        .order_by(*_job_order())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def get_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> SysCelery | None:
    """Fetch one job by id under workspace scope."""

    result = await session.execute(
        select(SysCelery).where(
            SysCelery.workspace_id == workspace_id,
            SysCelery.id == job_id,
        )
    )
    return result.scalar_one_or_none()
