"""Async queries for tenant-scoped sys_role and sys_role_permission."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization.models import SysPermission, SysRolePermission
from app.core.domain.identity.models import Tenant, Workspace
from app.exceptions import AppError
from app.sys.role.domain.db.models import SysRole


def _role_list_order():
    """Sort roles by display order then creation time."""

    return (SysRole.role_sort.asc(), SysRole.create_at.desc())


def _roles_in_workspace_filter(*, workspace_id: uuid.UUID, tenant_id: uuid.UUID):
    """Match tenant-wide or workspace-specific roles."""

    return (
        SysRole.tenant_id == tenant_id,
        or_(SysRole.workspace_id.is_(None), SysRole.workspace_id == workspace_id),
    )


async def get_tenant_id_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> uuid.UUID | None:
    """Return tenant id for a workspace row."""

    result = await session.execute(
        select(Workspace.tenant_id).where(Workspace.id == workspace_id)
    )
    return result.scalar_one_or_none()


async def count_roles_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> int:
    """Count roles visible in a workspace."""

    tenant_id = await get_tenant_id_for_workspace(
        session, workspace_id=workspace_id
    )
    if tenant_id is None:
        return 0
    stmt = select(func.count()).select_from(SysRole).where(
        *_roles_in_workspace_filter(workspace_id=workspace_id, tenant_id=tenant_id)
    )
    if role_name:
        stmt = stmt.where(SysRole.role_name.ilike(f"%{role_name.strip()}%"))
    if status is not None:
        stmt = stmt.where(SysRole.status == status)
    if role_key:
        stmt = stmt.where(SysRole.role_key == role_key.strip())
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_roles_for_workspace_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> Sequence[SysRole]:
    """Return one page of roles visible in a workspace."""

    tenant_id = await get_tenant_id_for_workspace(
        session, workspace_id=workspace_id
    )
    if tenant_id is None:
        return []
    stmt = (
        select(SysRole)
        .where(*_roles_in_workspace_filter(workspace_id=workspace_id, tenant_id=tenant_id))
        .order_by(*_role_list_order())
        .limit(limit)
        .offset(offset)
    )
    if role_name:
        stmt = stmt.where(SysRole.role_name.ilike(f"%{role_name.strip()}%"))
    if status is not None:
        stmt = stmt.where(SysRole.status == status)
    if role_key:
        stmt = stmt.where(SysRole.role_key == role_key.strip())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_role_by_id(
    session: AsyncSession, role_id: uuid.UUID
) -> SysRole | None:
    """Load one role by primary key."""

    return await session.get(SysRole, role_id)


async def get_role_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
) -> SysRole | None:
    """Load a role when it is visible in the given workspace."""

    tenant_id = await get_tenant_id_for_workspace(
        session, workspace_id=workspace_id
    )
    if tenant_id is None:
        return None
    result = await session.execute(
        select(SysRole).where(
            SysRole.id == role_id,
            *_roles_in_workspace_filter(workspace_id=workspace_id, tenant_id=tenant_id),
        )
    )
    return result.scalar_one_or_none()


async def get_role_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
) -> SysRole | None:
    """Load a role when it belongs to a tenant."""

    result = await session.execute(
        select(SysRole).where(
            SysRole.id == role_id,
            SysRole.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def add_role(session: AsyncSession, row: SysRole) -> SysRole:
    """Insert a role row and flush."""

    session.add(row)
    await session.flush()
    return row


async def delete_role(session: AsyncSession, role_id: uuid.UUID) -> None:
    """Delete one role row."""

    row = await session.get(SysRole, role_id)
    if row is not None:
        await session.delete(row)
        await session.flush()


async def list_menu_ids_for_role(
    session: AsyncSession, role_id: uuid.UUID
) -> list[uuid.UUID]:
    """Return menu ids linked to a role via sys_role_permission."""

    result = await session.execute(
        select(SysPermission.menu_id)
        .select_from(SysRolePermission)
        .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
        .where(
            SysRolePermission.role_id == role_id,
            SysPermission.menu_id.is_not(None),
        )
    )
    return list(result.scalars().all())


async def list_menu_ids_for_roles(
    session: AsyncSession, role_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Return distinct menu ids linked to any of the given roles."""

    if not role_ids:
        return []
    result = await session.execute(
        select(SysPermission.menu_id)
        .select_from(SysRolePermission)
        .join(SysPermission, SysPermission.id == SysRolePermission.permission_id)
        .where(
            SysRolePermission.role_id.in_(role_ids),
            SysPermission.menu_id.is_not(None),
        )
        .distinct()
    )
    return list(result.scalars().all())


async def delete_role_permissions(session: AsyncSession, role_id: uuid.UUID) -> None:
    """Remove all permission links for a role."""

    await session.execute(
        delete(SysRolePermission).where(SysRolePermission.role_id == role_id)
    )
    await session.flush()


async def replace_role_menus(
    session: AsyncSession,
    *,
    role_id: uuid.UUID,
    menu_ids: list[uuid.UUID],
) -> None:
    """Replace role permissions derived from menu ids."""

    await delete_role_permissions(session, role_id=role_id)
    if not menu_ids:
        return
    result = await session.execute(
        select(SysPermission.id, SysPermission.menu_id).where(
            SysPermission.menu_id.in_(menu_ids)
        )
    )
    by_menu = {row.menu_id: row.id for row in result.all()}
    missing = [mid for mid in menu_ids if mid not in by_menu]
    if missing:
        raise AppError(
            "role.invalid_menu_ids",
            "One or more menu ids have no permission catalog entry",
            400,
        )
    for menu_id in menu_ids:
        session.add(
            SysRolePermission(role_id=role_id, permission_id=by_menu[menu_id])
        )
    await session.flush()


@dataclass(frozen=True)
class RoleListRow:
    """Role ORM row plus display names for list API."""

    role: SysRole
    tenant_name: str
    workspace_name: str


def _roles_scoped_base_stmt(
    *,
    tenant_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
):
    """Base SELECT for tenant/platform role lists (workspace-bound roles only)."""

    stmt = (
        select(SysRole, Tenant.name, Workspace.name)
        .join(Tenant, Tenant.id == SysRole.tenant_id)
        .join(Workspace, Workspace.id == SysRole.workspace_id)
        .where(SysRole.workspace_id.is_not(None))
    )
    if tenant_id is not None:
        stmt = stmt.where(SysRole.tenant_id == tenant_id)
    if workspace_id is not None:
        stmt = stmt.where(SysRole.workspace_id == workspace_id)
    return stmt


def _apply_role_list_filters(
    stmt,
    *,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
):
    """Apply shared list filters used by scoped count and page queries."""

    if role_name:
        stmt = stmt.where(SysRole.role_name.ilike(f"%{role_name.strip()}%"))
    if status is not None:
        stmt = stmt.where(SysRole.status == status)
    if role_key:
        stmt = stmt.where(SysRole.role_key == role_key.strip())
    return stmt


async def validate_workspace_in_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Raise role.workspace_invalid when workspace missing or wrong tenant."""

    ws = await session.get(Workspace, workspace_id)
    if ws is None or ws.tenant_id != tenant_id:
        raise AppError("role.workspace_invalid", "Workspace not found", 400)


async def count_roles_scoped(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> int:
    """Count workspace-bound roles for platform or tenant scope."""

    stmt = _roles_scoped_base_stmt(tenant_id=tenant_id, workspace_id=workspace_id)
    stmt = _apply_role_list_filters(
        stmt, role_name=role_name, status=status, role_key=role_key
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    result = await session.execute(count_stmt)
    return int(result.scalar_one() or 0)


async def list_roles_scoped_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> Sequence[RoleListRow]:
    """Return one page of scoped roles with tenant/workspace names."""

    stmt = _roles_scoped_base_stmt(tenant_id=tenant_id, workspace_id=workspace_id)
    stmt = _apply_role_list_filters(
        stmt, role_name=role_name, status=status, role_key=role_key
    )
    stmt = stmt.order_by(*_role_list_order()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [
        RoleListRow(role=row, tenant_name=t_name, workspace_name=ws_name)
        for row, t_name, ws_name in result.all()
    ]
