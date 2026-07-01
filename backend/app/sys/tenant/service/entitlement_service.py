"""Tenant entitlement and tenant-admin grant management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization.models import GrantScopeType, GrantType, SysTenantEntitlement, SysUserGrant
from app.core.domain.identity.models import User
from app.core.security.permission_codes import FEATURE_CODES
from app.exceptions import AppError
from app.sys.tenant.service import tenant_service as tenant_svc


def _utc_now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(UTC)


async def list_entitlements(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[str]:
    """Return enabled feature codes for a tenant."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    r = await session.execute(
        select(SysTenantEntitlement.feature_code).where(
            SysTenantEntitlement.tenant_id == tenant_id,
            SysTenantEntitlement.enabled.is_(True),
        )
    )
    return list(r.scalars().all())


async def replace_entitlements(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    feature_codes: list[str],
    granted_by_user_id: uuid.UUID,
) -> list[str]:
    """Replace tenant feature entitlements with the given enabled codes."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    invalid = [c for c in feature_codes if c not in FEATURE_CODES]
    if invalid:
        raise AppError(
            "tenant.invalid_feature",
            f"Unknown feature codes: {', '.join(invalid)}",
            400,
        )
    await session.execute(
        delete(SysTenantEntitlement).where(SysTenantEntitlement.tenant_id == tenant_id)
    )
    now = _utc_now()
    unique_codes = sorted(set(feature_codes))
    for code in unique_codes:
        session.add(
            SysTenantEntitlement(
                tenant_id=tenant_id,
                feature_code=code,
                enabled=True,
                granted_by_user_id=granted_by_user_id,
                create_at=now,
                update_at=now,
            )
        )
    await session.commit()
    return unique_codes


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
