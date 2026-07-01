"""Persistence queries for authorization grants and permissions."""

from __future__ import annotations

import uuid

from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, or_, select
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
from app.sys.role.infrastructure import repository as role_repo


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


def _role_grant_scope_filter(
    *,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
):
    """SQL filter for role grants effective in one workspace."""

    clauses = [
        and_(
            SysUserGrant.scope_type == GrantScopeType.workspace.value,
            SysUserGrant.scope_id == workspace_id,
        )
    ]
    if tenant_id is not None:
        clauses.append(
            and_(
                SysUserGrant.scope_type == GrantScopeType.tenant.value,
                SysUserGrant.scope_id == tenant_id,
            )
        )
    return or_(*clauses)


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
        _role_grant_scope_filter(
            workspace_id=workspace_id, tenant_id=tenant_id
        ),
    )
    r = await session.execute(q)
    role_ids: list[uuid.UUID] = []
    for role_id in r.scalars().all():
        if role_id is not None:
            role_ids.append(role_id)
    if role_ids:
        return role_ids
    return []


async def replace_role_grants_in_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_ids: list[uuid.UUID],
    granted_by_user_id: uuid.UUID,
) -> None:
    """Replace workspace-scoped role grants for one user (dual-write companion)."""

    await delete_role_grants_in_workspace(
        session, workspace_id=workspace_id, user_id=user_id
    )
    now = datetime.now(UTC)
    for role_id in role_ids:
        session.add(
            SysUserGrant(
                user_id=user_id,
                grant_type=GrantType.role.value,
                role_id=role_id,
                scope_type=GrantScopeType.workspace.value,
                scope_id=workspace_id,
                granted_by_user_id=granted_by_user_id,
                status=True,
                create_at=now,
                update_at=now,
            )
        )
    await session.flush()


async def delete_role_grants_in_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Delete workspace-scoped role grants for one user."""

    await session.execute(
        delete(SysUserGrant).where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.role.value,
            SysUserGrant.scope_type == GrantScopeType.workspace.value,
            SysUserGrant.scope_id == workspace_id,
        )
    )
    await session.flush()


async def delete_all_grants_for_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> None:
    """Delete every grant row for a user."""

    await session.execute(delete(SysUserGrant).where(SysUserGrant.user_id == user_id))
    await session.flush()


async def delete_all_role_grants_for_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> None:
    """Delete every role grant row for a user."""

    await session.execute(
        delete(SysUserGrant).where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.role.value,
        )
    )
    await session.flush()


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


async def load_menu_ids_for_roles(
    session: AsyncSession, *, role_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Union menu ids from sys_role_permission -> sys_permission."""

    if not role_ids:
        return set()
    menu_ids = await role_repo.list_menu_ids_for_roles(session, role_ids)
    return set(menu_ids)


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
    if workspace_id is not None:
        q = q.where(
            _role_grant_scope_filter(
                workspace_id=workspace_id, tenant_id=tenant_id
            )
        )
    elif tenant_id is not None:
        q = q.where(
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
        )
    r = await session.execute(q)
    return set(r.scalars().all())


async def has_any_tenant_admin_grant(
    session: AsyncSession, *, user_id: uuid.UUID
) -> bool:
    """True when the user holds any active tenant_admin grant."""

    r = await session.execute(
        select(SysUserGrant.id)
        .where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.status.is_(True),
        )
        .limit(1)
    )
    return r.scalar_one_or_none() is not None


async def list_permissions_page(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    perm_type: str | None = None,
    perm_code: str | None = None,
) -> tuple[list[SysPermission], int]:
    """Return paginated rows from the global permission catalog."""

    stmt = select(SysPermission)
    if perm_type:
        stmt = stmt.where(SysPermission.perm_type == perm_type)
    if perm_code:
        stmt = stmt.where(SysPermission.perm_code.ilike(f"%{perm_code.strip()}%"))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one() or 0)
    offset = max(0, (page - 1) * page_size)
    rows = (
        await session.execute(
            stmt.order_by(SysPermission.perm_code.asc())
            .limit(page_size)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def list_all_menu_ids(session: AsyncSession) -> set[uuid.UUID]:
    """Return every sys_menu id (super-admin nav baseline)."""

    r = await session.execute(select(SysMenu.id))
    return set(r.scalars().all())
