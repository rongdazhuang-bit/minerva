"""Tenant-scoped user grant listing and mutation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization.models import (
    GrantScopeType,
    GrantType,
    SysPermission,
    SysUserGrant,
)
from app.core.domain.authorization.repository import is_tenant_admin
from app.core.domain.identity.models import MembershipRole, User, Workspace
from app.core.domain.identity.services import find_workspace_role_for_user
from app.exceptions import AppError
from app.sys.role.infrastructure import repository as role_repo
from app.sys.tenant.service import tenant_service as tenant_svc


def _utc_now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(UTC)


def _grant_to_dict(row: SysUserGrant) -> dict[str, Any]:
    """Serialize one grant row for API responses."""

    return {
        "id": row.id,
        "user_id": row.user_id,
        "grant_type": row.grant_type,
        "role_id": row.role_id,
        "permission_id": row.permission_id,
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "status": row.status,
        "create_at": row.create_at,
        "update_at": row.update_at,
    }


async def _tenant_workspace_ids(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return workspace ids belonging to a tenant."""

    r = await session.execute(
        select(Workspace.id).where(Workspace.tenant_id == tenant_id)
    )
    return set(r.scalars().all())


async def _actor_is_tenant_admin(
    session: AsyncSession, *, actor_user_id: uuid.UUID, tenant_id: uuid.UUID
) -> bool:
    """Return whether the actor holds tenant administrator grant."""

    return await is_tenant_admin(
        session, user_id=actor_user_id, tenant_id=tenant_id
    )


async def _assert_actor_may_manage_grant(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    grant_type: str,
    scope_type: str,
    scope_id: uuid.UUID | None,
) -> None:
    """Allow tenant admin, super-admin, or workspace admin (workspace role grants only)."""

    actor = await session.get(User, actor_user_id)
    if actor is not None and actor.is_super_admin:
        return
    if await _actor_is_tenant_admin(
        session, actor_user_id=actor_user_id, tenant_id=tenant_id
    ):
        return
    if grant_type != GrantType.role.value:
        raise AppError("grant.forbidden", "Workspace admin may only manage role grants", 403)
    if scope_type != GrantScopeType.workspace.value or scope_id is None:
        raise AppError("grant.forbidden", "Workspace admin may only manage workspace grants", 403)
    ws = await session.get(Workspace, scope_id)
    if ws is None or ws.tenant_id != tenant_id:
        raise AppError("grant.forbidden", "Workspace not in tenant", 403)
    role = await find_workspace_role_for_user(
        session, user_id=actor_user_id, workspace_id=scope_id
    )
    if role != MembershipRole.admin:
        raise AppError("grant.forbidden", "Workspace admin required", 403)


async def resolve_list_workspace_filter(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Restrict workspace-admin list queries to one workspace."""

    actor = await session.get(User, actor_user_id)
    if actor is not None and actor.is_super_admin:
        return workspace_id
    if await _actor_is_tenant_admin(
        session, actor_user_id=actor_user_id, tenant_id=tenant_id
    ):
        return workspace_id
    admin_workspaces = await _admin_workspace_ids_in_tenant(
        session, actor_user_id=actor_user_id, tenant_id=tenant_id
    )
    if not admin_workspaces:
        raise AppError("grant.forbidden", "Grant manager required", 403)
    if workspace_id is not None:
        if workspace_id not in admin_workspaces:
            raise AppError("grant.forbidden", "Workspace not manageable", 403)
        return workspace_id
    if len(admin_workspaces) == 1:
        return next(iter(admin_workspaces))
    raise AppError(
        "grant.workspace_required",
        "workspace_id query parameter is required",
        400,
    )


async def _admin_workspace_ids_in_tenant(
    session: AsyncSession, *, actor_user_id: uuid.UUID, tenant_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return workspace ids in a tenant where the actor is workspace admin."""

    from app.core.domain.identity.models import WorkspaceMembership

    r = await session.execute(
        select(WorkspaceMembership.workspace_id)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == actor_user_id,
            WorkspaceMembership.role == MembershipRole.admin,
            Workspace.tenant_id == tenant_id,
        )
    )
    return set(r.scalars().all())


async def list_grants_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    page: int,
    page_size: int,
    grant_type: str | None = None,
    user_id: uuid.UUID | None = None,
    scope_type: str | None = None,
    workspace_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated grants visible within one tenant."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    if actor_user_id is not None:
        workspace_id = await resolve_list_workspace_filter(
            session,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        if scope_type is None and workspace_id is not None:
            scope_type = GrantScopeType.workspace.value
    workspace_ids = await _tenant_workspace_ids(session, tenant_id=tenant_id)
    stmt = select(SysUserGrant).where(
        SysUserGrant.grant_type != GrantType.tenant_admin.value,
    )
    tenant_scope = (SysUserGrant.scope_type == GrantScopeType.tenant.value) & (
        SysUserGrant.scope_id == tenant_id
    )
    if workspace_ids:
        workspace_scope = (
            SysUserGrant.scope_type == GrantScopeType.workspace.value
        ) & SysUserGrant.scope_id.in_(workspace_ids)
        stmt = stmt.where(tenant_scope | workspace_scope)
    else:
        stmt = stmt.where(tenant_scope)
    if grant_type:
        stmt = stmt.where(SysUserGrant.grant_type == grant_type)
    if user_id is not None:
        stmt = stmt.where(SysUserGrant.user_id == user_id)
    if scope_type:
        stmt = stmt.where(SysUserGrant.scope_type == scope_type)
    if workspace_id is not None:
        if workspace_id not in workspace_ids:
            raise AppError("grant.workspace_invalid", "Workspace not in tenant", 400)
        stmt = stmt.where(
            SysUserGrant.scope_type == GrantScopeType.workspace.value,
            SysUserGrant.scope_id == workspace_id,
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one() or 0)
    offset = max(0, (page - 1) * page_size)
    rows = (
        await session.execute(
            stmt.order_by(SysUserGrant.create_at.desc())
            .limit(page_size)
            .offset(offset)
        )
    ).scalars().all()
    return [_grant_to_dict(row) for row in rows], total


async def create_grant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    grant_type: str,
    role_id: uuid.UUID | None,
    permission_id: uuid.UUID | None,
    scope_type: str,
    scope_id: uuid.UUID | None,
    granted_by_user_id: uuid.UUID,
) -> dict[str, Any]:
    """Create one role or direct_permission grant within tenant scope."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("grant.user_not_found", "User not found", 404)
    if grant_type not in {
        GrantType.role.value,
        GrantType.direct_permission.value,
    }:
        raise AppError("grant.invalid_type", "Invalid grant_type", 400)
    workspace_ids = await _tenant_workspace_ids(session, tenant_id=tenant_id)
    if scope_type == GrantScopeType.tenant.value:
        if scope_id is not None and scope_id != tenant_id:
            raise AppError("grant.scope_invalid", "Tenant scope_id mismatch", 400)
        scope_id = tenant_id
    elif scope_type == GrantScopeType.workspace.value:
        if scope_id is None or scope_id not in workspace_ids:
            raise AppError("grant.workspace_invalid", "Workspace not in tenant", 400)
    else:
        raise AppError("grant.scope_invalid", "Invalid scope_type", 400)
    await _assert_actor_may_manage_grant(
        session,
        actor_user_id=granted_by_user_id,
        tenant_id=tenant_id,
        grant_type=grant_type,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    if grant_type == GrantType.role.value:
        if role_id is None:
            raise AppError("grant.role_required", "role_id is required", 400)
        if scope_type == GrantScopeType.workspace.value:
            role = await role_repo.get_role_for_workspace(
                session, workspace_id=scope_id, role_id=role_id
            )
        else:
            role = await role_repo.get_role_for_tenant(
                session, tenant_id=tenant_id, role_id=role_id
            )
        if role is None or not role.status:
            raise AppError("grant.role_invalid", "Invalid role_id", 400)
        if role.tenant_id != tenant_id:
            raise AppError("grant.role_invalid", "Role tenant mismatch", 400)
        permission_id = None
    else:
        if permission_id is None:
            raise AppError(
                "grant.permission_required",
                "permission_id is required",
                400,
            )
        perm = await session.get(SysPermission, permission_id)
        if perm is None or not perm.status:
            raise AppError("grant.permission_invalid", "Invalid permission_id", 400)
        role_id = None
    now = _utc_now()
    row = SysUserGrant(
        user_id=user_id,
        grant_type=grant_type,
        role_id=role_id,
        permission_id=permission_id,
        scope_type=scope_type,
        scope_id=scope_id,
        granted_by_user_id=granted_by_user_id,
        status=True,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _grant_to_dict(row)


async def delete_grant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    grant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    """Revoke one grant when it belongs to the tenant scope."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    row = await session.get(SysUserGrant, grant_id)
    if row is None:
        raise AppError("grant.not_found", "Grant not found", 404)
    if row.grant_type == GrantType.tenant_admin.value:
        raise AppError("grant.forbidden", "Cannot delete tenant_admin grant here", 403)
    await _assert_actor_may_manage_grant(
        session,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        grant_type=row.grant_type,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
    )
    workspace_ids = await _tenant_workspace_ids(session, tenant_id=tenant_id)
    in_tenant = (
        row.scope_type == GrantScopeType.tenant.value and row.scope_id == tenant_id
    ) or (
        row.scope_type == GrantScopeType.workspace.value
        and row.scope_id in workspace_ids
    )
    if not in_tenant:
        raise AppError("grant.not_found", "Grant not found", 404)
    await session.delete(row)
    await session.commit()
