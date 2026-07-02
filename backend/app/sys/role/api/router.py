"""Platform and tenant-scoped routes for sys_role and menu permissions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.identity.models import User
from app.core.security.permission_resolver import parse_uuid_claim
from app.dependencies import get_db
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.role.api.deps import (
    require_super_admin,
    require_tenant_role_manager,
    require_tenant_role_viewer,
)
from app.sys.role.api.schemas import (
    SysRoleCapabilitiesOut,
    SysRoleCreateIn,
    SysRoleDetailOut,
    SysRoleListItemOut,
    SysRoleListPageOut,
    SysRolePatchIn,
)
from app.sys.role.infrastructure.repository import RoleListRow
from app.sys.role.service import role_service as svc

platform_router = APIRouter(prefix="/sys/roles", tags=["roles"])
tenant_router = APIRouter(prefix="/sys/tenants/{tenant_id}/roles", tags=["roles"])


def _row_to_list_item(row: RoleListRow) -> SysRoleListItemOut:
    """Project scoped list row to API list item schema."""

    r = row.role
    return SysRoleListItemOut(
        id=r.id,
        tenant_id=r.tenant_id,
        tenant_name=row.tenant_name,
        workspace_id=r.workspace_id,
        workspace_name=row.workspace_name,
        role_name=r.role_name,
        role_key=r.role_key,
        role_sort=r.role_sort,
        status=r.status,
        remark=r.remark,
        create_at=r.create_at,
        update_at=r.update_at,
    )


@platform_router.get("/meta/capabilities", response_model=SysRoleCapabilitiesOut)
async def get_role_capabilities(
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> SysRoleCapabilitiesOut:
    """Return role UI capability flags derived from JWT tenant context."""

    tid = None
    if cred is not None:
        payload = _decode_access_payload(cred)
        tid = parse_uuid_claim(payload, "tid")
    data = await svc.get_role_capabilities(
        session,
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        jwt_tenant_id=tid,
    )
    return SysRoleCapabilitiesOut.model_validate(data)


@platform_router.get("/menu-tree", response_model=list[SysMenuNodeOut])
async def list_role_menu_tree(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[SysMenuNodeOut]:
    """Return full menu tree for role permission assignment."""

    return await svc.list_menu_tree_for_role_assignment(session)


@platform_router.get("", response_model=SysRoleListPageOut)
async def list_roles_platform(
    tenant_id: uuid.UUID | None = Query(default=None),
    workspace_id: uuid.UUID | None = Query(default=None),
    role_name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    role_key: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysRoleListPageOut:
    """Return paginated roles across tenants for super admins."""

    rows, total = await svc.list_roles_scoped_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return SysRoleListPageOut(
        items=[_row_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@tenant_router.get("/menu-tree", response_model=list[SysMenuNodeOut])
async def list_role_menu_tree_for_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _viewer: uuid.UUID = Depends(require_tenant_role_viewer),
) -> list[SysMenuNodeOut]:
    """Return tenant-scoped menu tree for role permission assignment."""

    return await svc.list_menu_tree_for_tenant_role_assignment(
        session,
        tenant_id=tenant_id,
    )


@tenant_router.get("", response_model=SysRoleListPageOut)
async def list_roles_for_tenant(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None = Query(default=None),
    role_name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    role_key: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _viewer: uuid.UUID = Depends(require_tenant_role_viewer),
) -> SysRoleListPageOut:
    """Return paginated roles for one tenant."""

    rows, total = await svc.list_roles_scoped_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return SysRoleListPageOut(
        items=[_row_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@tenant_router.post("", response_model=SysRoleDetailOut, status_code=201)
async def create_role(
    tenant_id: uuid.UUID,
    body: SysRoleCreateIn,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> SysRoleDetailOut:
    """Create a workspace-bound role under a tenant."""

    row = await svc.create_role_for_tenant(
        session, tenant_id=tenant_id, data=body.model_dump()
    )
    detail_row, menu_ids, t_name, ws_name = await svc.get_role_detail_for_tenant(
        session, tenant_id=tenant_id, role_id=row.id
    )
    base = _row_to_list_item(
        RoleListRow(role=detail_row, tenant_name=t_name, workspace_name=ws_name)
    )
    return SysRoleDetailOut(**base.model_dump(), menu_ids=menu_ids)


@tenant_router.get("/{role_id}", response_model=SysRoleDetailOut)
async def get_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _viewer: uuid.UUID = Depends(require_tenant_role_viewer),
) -> SysRoleDetailOut:
    """Return one tenant-scoped role with menu ids."""

    row, menu_ids, t_name, ws_name = await svc.get_role_detail_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    base = _row_to_list_item(
        RoleListRow(role=row, tenant_name=t_name, workspace_name=ws_name)
    )
    return SysRoleDetailOut(**base.model_dump(), menu_ids=menu_ids)


@tenant_router.patch("/{role_id}", response_model=SysRoleDetailOut)
async def patch_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    body: SysRolePatchIn,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> SysRoleDetailOut:
    """Partially update a tenant-scoped role."""

    await svc.update_role_for_tenant(
        session,
        tenant_id=tenant_id,
        role_id=role_id,
        patch=body.model_dump(exclude_unset=True),
    )
    row, menu_ids, t_name, ws_name = await svc.get_role_detail_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    base = _row_to_list_item(
        RoleListRow(role=row, tenant_name=t_name, workspace_name=ws_name)
    )
    return SysRoleDetailOut(**base.model_dump(), menu_ids=menu_ids)


@tenant_router.delete("/{role_id}", status_code=204)
async def delete_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> Response:
    """Delete a tenant-scoped role and its menu links."""

    await svc.delete_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
