"""Workspace-scoped role CRUD and menu permission assignment."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.menu.infrastructure import repository as menu_repo
from app.sys.menu.service import menu_service as menu_svc
from app.sys.role.domain.db.models import SysRole
from app.sys.role.infrastructure import repository as repo


def _utc_now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(UTC)


def _is_unique_violation(exc: IntegrityError) -> bool:
    """True when the DB error is a unique constraint violation."""

    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "pgcode", None) == "23505":
        return True
    return "unique" in str(exc).lower()


async def _commit_or_conflict(session: AsyncSession) -> None:
    """Commit or map unique violations to role.conflict."""

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if _is_unique_violation(e):
            raise AppError(
                "role.conflict",
                "Duplicate role_key in tenant",
                409,
            ) from e
        raise


async def _validate_menu_ids(session: AsyncSession, menu_ids: list[uuid.UUID]) -> None:
    """Ensure every menu id exists in global sys_menu."""

    if not menu_ids:
        return
    rows = await menu_repo.list_all(session)
    valid = {r.id for r in rows}
    invalid = [mid for mid in menu_ids if mid not in valid]
    if invalid:
        raise AppError(
            "role.invalid_menu_ids",
            "One or more menu ids do not exist",
            400,
        )


async def _require_role(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
) -> SysRole:
    """Load a role or raise role.not_found when missing or wrong workspace."""

    row = await repo.get_role_for_workspace(
        session, workspace_id=workspace_id, role_id=role_id
    )
    if row is None:
        raise AppError("role.not_found", "Role not found", 404)
    return row


async def list_roles_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> tuple[list[SysRole], int]:
    """Return paginated roles and total count for a workspace."""

    total = await repo.count_roles_for_workspace(
        session,
        workspace_id=workspace_id,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    offset = (page - 1) * page_size
    rows = await repo.list_roles_for_workspace_page(
        session,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return list(rows), total


async def get_role_detail(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
) -> tuple[SysRole, list[uuid.UUID]]:
    """Return role row and linked menu ids."""

    row = await _require_role(session, workspace_id=workspace_id, role_id=role_id)
    menu_ids = await repo.list_menu_ids_for_role(session, role_id)
    return row, menu_ids


async def create_role(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    data: dict[str, Any],
) -> SysRole:
    """Create a role and optional menu links."""

    menu_ids: list[uuid.UUID] = list(data.get("menu_ids") or [])
    await _validate_menu_ids(session, menu_ids)
    tenant_id = await repo.get_tenant_id_for_workspace(
        session, workspace_id=workspace_id
    )
    if tenant_id is None:
        raise AppError("role.workspace_invalid", "Workspace not found", 404)
    now = _utc_now()
    row = SysRole(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        role_name=str(data["role_name"]).strip(),
        role_key=str(data["role_key"]).strip(),
        role_sort=int(data.get("role_sort") or 0),
        status=bool(data.get("status", True)),
        remark=data.get("remark"),
        create_at=now,
        update_at=now,
    )
    await repo.add_role(session, row)
    if menu_ids:
        await repo.replace_role_menus(session, role_id=row.id, menu_ids=menu_ids)
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def update_role(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysRole:
    """Patch role fields and optionally replace menu links."""

    row = await _require_role(session, workspace_id=workspace_id, role_id=role_id)
    if "role_name" in patch and patch["role_name"] is not None:
        row.role_name = str(patch["role_name"]).strip()
    if "role_key" in patch and patch["role_key"] is not None:
        row.role_key = str(patch["role_key"]).strip()
    if "role_sort" in patch and patch["role_sort"] is not None:
        row.role_sort = int(patch["role_sort"])
    if "status" in patch and patch["status"] is not None:
        row.status = bool(patch["status"])
    if "remark" in patch:
        row.remark = patch["remark"]
    if "menu_ids" in patch and patch["menu_ids"] is not None:
        menu_ids = list(patch["menu_ids"])
        await _validate_menu_ids(session, menu_ids)
        await repo.replace_role_menus(session, role_id=row.id, menu_ids=menu_ids)
    row.update_at = _utc_now()
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def delete_role(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
) -> None:
    """Delete role and all menu links in one transaction."""

    await _require_role(session, workspace_id=workspace_id, role_id=role_id)
    await repo.delete_role_permissions(session, role_id)
    await repo.delete_role(session, role_id)
    await session.commit()


async def list_menu_tree_for_role_assignment(
    session: AsyncSession,
) -> list[SysMenuNodeOut]:
    """Return full M/C/F menu tree for role permission picker."""

    return await menu_svc.list_menu_tree(session)


def build_role_capabilities(
    *,
    is_super_admin: bool,
    is_tenant_admin: bool,
    jwt_tenant_id: uuid.UUID | None,
    jwt_tenant_name: str | None,
) -> dict[str, object]:
    """Build role form/list capability flags for the current actor."""

    can_pick_tenant = is_super_admin
    can_pick_workspace = is_super_admin or is_tenant_admin
    fixed_tenant_id = None if is_super_admin else jwt_tenant_id
    fixed_tenant_name = None if is_super_admin else jwt_tenant_name
    default_filter_tenant_id = None if is_super_admin else jwt_tenant_id
    default_filter_workspace_id = None
    return {
        "is_super_admin": is_super_admin,
        "is_tenant_admin": is_tenant_admin,
        "can_pick_tenant": can_pick_tenant,
        "can_pick_workspace": can_pick_workspace,
        "fixed_tenant_id": fixed_tenant_id,
        "fixed_tenant_name": fixed_tenant_name,
        "default_filter_tenant_id": default_filter_tenant_id,
        "default_filter_workspace_id": default_filter_workspace_id,
    }


async def get_role_capabilities(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    is_super_admin: bool,
    jwt_tenant_id: uuid.UUID | None,
) -> dict[str, object]:
    """Resolve capabilities using JWT tenant and grant checks."""

    from app.core.domain.authorization.repository import is_tenant_admin
    from app.core.domain.identity.models import Tenant

    is_ta = False
    tenant_name = None
    if jwt_tenant_id is not None:
        is_ta = await is_tenant_admin(
            session, user_id=user_id, tenant_id=jwt_tenant_id
        )
        tenant = await session.get(Tenant, jwt_tenant_id)
        tenant_name = tenant.name if tenant else None
    return build_role_capabilities(
        is_super_admin=is_super_admin,
        is_tenant_admin=is_ta,
        jwt_tenant_id=jwt_tenant_id,
        jwt_tenant_name=tenant_name,
    )


async def list_roles_scoped_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    page: int,
    page_size: int,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> tuple[list[repo.RoleListRow], int]:
    """Paginate roles for platform or tenant scope."""

    total = await repo.count_roles_scoped(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    offset = (page - 1) * page_size
    rows = await repo.list_roles_scoped_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return list(rows), total


async def create_role_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    data: dict[str, Any],
) -> SysRole:
    """Create a workspace-bound role under a tenant path."""

    workspace_id = uuid.UUID(str(data["workspace_id"]))
    await repo.validate_workspace_in_tenant(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    menu_ids: list[uuid.UUID] = list(data.get("menu_ids") or [])
    await _validate_menu_ids(session, menu_ids)
    now = _utc_now()
    row = SysRole(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        role_name=str(data["role_name"]).strip(),
        role_key=str(data["role_key"]).strip(),
        role_sort=int(data.get("role_sort") or 0),
        status=bool(data.get("status", True)),
        remark=data.get("remark"),
        create_at=now,
        update_at=now,
    )
    await repo.add_role(session, row)
    if menu_ids:
        await repo.replace_role_menus(session, role_id=row.id, menu_ids=menu_ids)
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def get_role_detail_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
) -> tuple[SysRole, list[uuid.UUID], str, str]:
    """Return role, menu ids, tenant name, workspace name."""

    from app.core.domain.identity.models import Tenant, Workspace

    row = await repo.get_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    if row is None or row.workspace_id is None:
        raise AppError("role.not_found", "Role not found", 404)
    menu_ids = await repo.list_menu_ids_for_role(session, role_id)
    tenant = await session.get(Tenant, tenant_id)
    ws = await session.get(Workspace, row.workspace_id)
    return (
        row,
        menu_ids,
        tenant.name if tenant else "",
        ws.name if ws else "",
    )


async def update_role_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysRole:
    """Patch role fields; ignore tenant_id/workspace_id in patch."""

    patch.pop("workspace_id", None)
    patch.pop("tenant_id", None)
    row = await repo.get_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    if row is None:
        raise AppError("role.not_found", "Role not found", 404)
    return await update_role(
        session,
        workspace_id=row.workspace_id,
        role_id=role_id,
        patch=patch,
    )


async def delete_role_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
) -> None:
    """Delete role scoped by tenant path."""

    row = await repo.get_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    if row is None or row.workspace_id is None:
        raise AppError("role.not_found", "Role not found", 404)
    await delete_role(session, workspace_id=row.workspace_id, role_id=role_id)
