"""Persistence helpers for sys_tenant and sys_workspaces."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import (
    Tenant,
    TenantMembership,
    User,
    Workspace,
    WorkspaceMembership,
)


async def count_tenants_page(
    session: AsyncSession,
    *,
    name: str | None,
    status: bool | None,
) -> int:
    """Count tenants matching optional filters."""

    stmt = select(func.count()).select_from(Tenant)
    if name:
        stmt = stmt.where(Tenant.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Tenant.status == status)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def list_tenants_page(
    session: AsyncSession,
    *,
    name: str | None,
    status: bool | None,
    offset: int,
    limit: int,
) -> list[Tenant]:
    """Return one page of tenants ordered by create_at DESC."""

    stmt = select(Tenant)
    if name:
        stmt = stmt.where(Tenant.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Tenant.status == status)
    stmt = stmt.order_by(Tenant.create_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_tenant(session: AsyncSession, *, tenant_id: uuid.UUID) -> Tenant | None:
    """Load tenant by primary key."""

    return await session.get(Tenant, tenant_id)


async def list_tenant_users(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[User]:
    """Return tenant members ordered by nickname then email."""

    r = await session.execute(
        select(User)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(User.nickname.asc(), User.email.asc())
    )
    return list(r.scalars().all())


async def list_platform_users_for_picker(
    session: AsyncSession, *, limit: int = 500
) -> list[User]:
    """Return active platform users for tenant admin picker on create form."""

    r = await session.execute(
        select(User)
        .where(User.status.is_(True))
        .order_by(User.nickname.asc(), User.email.asc())
        .limit(limit)
    )
    return list(r.scalars().all())


async def count_workspaces_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str | None,
    status: bool | None,
) -> int:
    """Count workspaces under a tenant."""

    stmt = (
        select(func.count())
        .select_from(Workspace)
        .where(Workspace.tenant_id == tenant_id)
    )
    if name:
        stmt = stmt.where(Workspace.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Workspace.status == status)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def list_workspaces_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str | None,
    status: bool | None,
    offset: int,
    limit: int,
) -> list[Workspace]:
    """Return one page of workspaces for a tenant."""

    stmt = select(Workspace).where(Workspace.tenant_id == tenant_id)
    if name:
        stmt = stmt.where(Workspace.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Workspace.status == status)
    stmt = stmt.order_by(Workspace.create_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_workspace_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Workspace | None:
    """Load workspace when it belongs to tenant_id."""

    stmt = select(Workspace).where(
        Workspace.id == workspace_id,
        Workspace.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_tenant_cascade(session: AsyncSession, *, tenant_id: uuid.UUID) -> None:
    """Delete tenant memberships, workspace memberships, workspaces, then tenant."""

    ws_ids = (
        await session.execute(
            select(Workspace.id).where(Workspace.tenant_id == tenant_id)
        )
    ).scalars().all()
    if ws_ids:
        await session.execute(
            delete(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id.in_(ws_ids)
            )
        )
    await session.execute(
        delete(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
    )
    await session.execute(delete(Workspace).where(Workspace.tenant_id == tenant_id))
    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def delete_workspace_row(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> int:
    """Delete only the sys_workspaces row; return rows affected."""

    result = await session.execute(
        delete(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.tenant_id == tenant_id,
        )
    )
    return result.rowcount or 0
