"""Persistence queries for workspace-scoped ``SysCelery`` jobs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.celery.domain.db.models import SysCelery


def _job_order():
    """Return default ordering for job list endpoints."""

    return (
        SysCelery.create_at.desc().nulls_last(),
        SysCelery.id.desc(),
    )


def _apply_workspace_filters(
    stmt: Any,
    *,
    workspace_id: uuid.UUID,
    name: str | None = None,
    task_code: str | None = None,
    task: str | None = None,
    enabled: bool | None = None,
) -> Any:
    """Apply workspace scope and optional list filters to query statement."""

    query = stmt.where(SysCelery.workspace_id == workspace_id)
    if name:
        query = query.where(SysCelery.name.ilike(f"%{name}%"))
    if task_code:
        query = query.where(SysCelery.task_code.ilike(f"%{task_code}%"))
    if task:
        query = query.where(SysCelery.task.ilike(f"%{task}%"))
    if enabled is not None:
        query = query.where(SysCelery.enabled.is_(enabled))
    return query


async def count_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str | None = None,
    task_code: str | None = None,
    task: str | None = None,
    enabled: bool | None = None,
) -> int:
    """Count total jobs under one workspace."""

    result = await session.execute(_apply_workspace_filters(
        select(func.count()).select_from(SysCelery),
        workspace_id=workspace_id,
        name=name,
        task_code=task_code,
        task=task,
        enabled=enabled,
    )
    )
    return int(result.scalar_one() or 0)


async def list_for_workspace_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
    name: str | None = None,
    task_code: str | None = None,
    task: str | None = None,
    enabled: bool | None = None,
) -> Sequence[SysCelery]:
    """List one page of jobs under workspace scope."""

    result = await session.execute(_apply_workspace_filters(
        select(SysCelery),
        workspace_id=workspace_id,
        name=name,
        task_code=task_code,
        task=task,
        enabled=enabled,
    )
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
