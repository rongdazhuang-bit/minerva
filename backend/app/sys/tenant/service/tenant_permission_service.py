"""Tenant menu permission and tenant-admin grant management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization.models import GrantScopeType, GrantType, SysTenantPermission, SysUserGrant
from app.core.domain.identity.models import User
from app.exceptions import AppError
from app.sys.menu.domain.db.models import SysMenu
from app.sys.tenant.service import tenant_service as tenant_svc


def _utc_now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(UTC)


async def list_tenant_menu_ids(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[uuid.UUID]:
    """Return enabled menu ids assigned to a tenant."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    r = await session.execute(
        select(SysTenantPermission.menu_id).where(
            SysTenantPermission.tenant_id == tenant_id,
            SysTenantPermission.enabled.is_(True),
        )
    )
    return list(r.scalars().all())


async def replace_tenant_permissions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    menu_ids: list[uuid.UUID],
    create_by: uuid.UUID,
) -> list[uuid.UUID]:
    """Replace tenant menu permissions with the given menu ids."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    unique_ids = list(dict.fromkeys(menu_ids))
    if unique_ids:
        r = await session.execute(
            select(SysMenu.id).where(SysMenu.id.in_(unique_ids))
        )
        found = set(r.scalars().all())
        invalid = [str(m) for m in unique_ids if m not in found]
        if invalid:
            raise AppError(
                "tenant.invalid_menu",
                f"Unknown menu ids: {', '.join(invalid)}",
                400,
            )
    await session.execute(
        delete(SysTenantPermission).where(SysTenantPermission.tenant_id == tenant_id)
    )
    now = _utc_now()
    for mid in unique_ids:
        session.add(
            SysTenantPermission(
                tenant_id=tenant_id,
                menu_id=mid,
                enabled=True,
                create_by=create_by,
                create_at=now,
                update_at=now,
            )
        )
    await session.commit()
    return unique_ids


async def list_tenant_admin_user_ids(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[uuid.UUID]:
    """Return user ids with active tenant_admin grant."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    r = await session.execute(
        select(SysUserGrant.user_id).where(
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
            SysUserGrant.status.is_(True),
        )
    )
    return list(r.scalars().all())


async def replace_tenant_admins(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    granted_by_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Replace tenant administrator grants for a tenant."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    for uid in user_ids:
        user = await session.get(User, uid)
        if user is None:
            raise AppError("tenant.admin_user_not_found", "User not found", 404)
    await session.execute(
        delete(SysUserGrant).where(
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
        )
    )
    now = _utc_now()
    unique_ids = list(dict.fromkeys(user_ids))
    for uid in unique_ids:
        session.add(
            SysUserGrant(
                user_id=uid,
                grant_type=GrantType.tenant_admin.value,
                scope_type=GrantScopeType.tenant.value,
                scope_id=tenant_id,
                granted_by_user_id=granted_by_user_id,
                status=True,
                create_at=now,
                update_at=now,
            )
        )
    await session.commit()
    return unique_ids


async def is_user_tenant_admin(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Return whether the user holds an active tenant_admin grant."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    r = await session.execute(
        select(SysUserGrant.id).where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
            SysUserGrant.status.is_(True),
        )
    )
    return r.scalar_one_or_none() is not None


async def set_user_tenant_admin(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    enabled: bool,
    granted_by_user_id: uuid.UUID,
) -> bool:
    """Enable or disable tenant_admin grant for one user."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("user.not_found", "User not found", 404)

    r = await session.execute(
        select(SysUserGrant).where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
        )
    )
    row = r.scalar_one_or_none()
    now = _utc_now()

    if enabled:
        if row is None:
            session.add(
                SysUserGrant(
                    user_id=user_id,
                    grant_type=GrantType.tenant_admin.value,
                    scope_type=GrantScopeType.tenant.value,
                    scope_id=tenant_id,
                    granted_by_user_id=granted_by_user_id,
                    status=True,
                    create_at=now,
                    update_at=now,
                )
            )
        else:
            row.status = True
            row.granted_by_user_id = granted_by_user_id
            row.update_at = now
        await session.commit()
        return True

    if row is not None:
        await session.delete(row)
        await session.commit()
    return False
