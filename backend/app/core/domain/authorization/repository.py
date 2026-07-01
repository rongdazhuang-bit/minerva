"""Persistence queries for authorization grants and permissions."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization.models import (
    GrantScopeType,
    GrantType,
    SysPermission,
    SysRolePermission,
    SysTenantEntitlement,
    SysUserGrant,
)
from app.sys.menu.domain.db.models import SysMenu
from app.sys.role.domain.db.models import SysRoleMenu
from app.sys.user.infrastructure import repository as user_repo


async def load_enabled_tenant_features(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[str]:
    """Return enabled feature_code values for a tenant."""

    r = await session.execute(
        select(SysTenantEntitlement.feature_code).where(
            SysTenantEntitlement.tenant_id == tenant_id,
            SysTenantEntitlement.enabled.is_(True),
        )
    )
    return list(r.scalars().all())


async def is_tenant_admin(
    session: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> bool:
    """True when the user has an active tenant_admin grant for the tenant."""

    r = await session.execute(
        select(SysUserGrant.id)
        .where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
            SysUserGrant.status.is_(True),
        )
        .limit(1)
    )
    return r.scalar_one_or_none() is not None


async def load_role_ids_from_grants(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Collect role ids from active role grants scoped to workspace or tenant."""

    q = select(SysUserGrant.role_id).where(
        SysUserGrant.user_id == user_id,
        SysUserGrant.grant_type == GrantType.role.value,
        SysUserGrant.status.is_(True),
        SysUserGrant.role_id.is_not(None),
    )
    r = await session.execute(q)
    role_ids: list[uuid.UUID] = []
    for role_id in r.scalars().all():
        if role_id is not None:
            role_ids.append(role_id)
    legacy = await user_repo.list_role_ids_for_user_in_workspace(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        enabled_only=True,
    )
    for rid in legacy:
        if rid not in role_ids:
            role_ids.append(rid)
    return role_ids


async def load_permission_codes_for_roles(
    session: AsyncSession, *, role_ids: list[uuid.UUID]
) -> set[str]:
    """Union permission codes linked to roles via sys_role_permission."""

    if not role_ids:
        return set()
    r = await session.execute(
        select(SysPermission.perm_code)
        .select_from(SysRolePermission)
        .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
        .where(
            SysRolePermission.role_id.in_(role_ids),
            SysPermission.status.is_(True),
        )
    )
    return set(r.scalars().all())


async def load_menu_ids_for_roles_dual(
    session: AsyncSession, *, role_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Union menu ids from legacy sys_role_menu (P0 dual-read)."""

    if not role_ids:
        return set()
    r = await session.execute(
        select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id.in_(role_ids))
    )
    return set(r.scalars().all())


async def load_direct_permission_codes(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
) -> set[str]:
    """Collect perm_code values from direct_permission grants in scope."""

    q = select(SysPermission.perm_code).select_from(SysUserGrant).join(
        SysPermission, SysPermission.id == SysUserGrant.permission_id
    ).where(
        SysUserGrant.user_id == user_id,
        SysUserGrant.grant_type == GrantType.direct_permission.value,
        SysUserGrant.status.is_(True),
    )
    r = await session.execute(q)
    return set(r.scalars().all())


async def list_all_menu_ids(session: AsyncSession) -> set[uuid.UUID]:
    """Return every sys_menu id (super-admin nav baseline)."""

    r = await session.execute(select(SysMenu.id))
    return set(r.scalars().all())
