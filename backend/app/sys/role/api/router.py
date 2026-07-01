"""CRUD routes for workspace-scoped sys_role and menu permissions."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import (
    require_workspace_member,
)
from app.dependencies import get_db
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.role.api.deps import require_tenant_role_manager
from app.sys.role.api.schemas import (
    SysRoleCreateIn,
    SysRoleDetailOut,
    SysRoleListItemOut,
    SysRoleListPageOut,
    SysRolePatchIn,
)
from app.sys.role.domain.db.models import SysRole
from app.sys.role.service import role_service as svc

router = APIRouter(prefix="/workspaces/{workspace_id}/roles", tags=["roles"])


def _to_list_item(row: SysRole) -> SysRoleListItemOut:
    """Project ORM row to list response schema."""

    return SysRoleListItemOut.model_validate(row)


def _create_payload(body: SysRoleCreateIn) -> dict[str, Any]:
    """Convert create body to service dict."""

    return body.model_dump()


def _patch_payload(body: SysRolePatchIn) -> dict[str, Any]:
    """Convert patch body to service dict excluding unset fields."""

    return body.model_dump(exclude_unset=True)


@router.get("", response_model=SysRoleListPageOut)
async def list_roles(
    workspace_id: uuid.UUID,
    role_name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    role_key: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> SysRoleListPageOut:
    """Return paginated roles for the current workspace."""

    rows, total = await svc.list_roles_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return SysRoleListPageOut(
        items=[_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/menu-tree", response_model=list[SysMenuNodeOut])
async def list_role_menu_tree(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> list[SysMenuNodeOut]:
    """Return full menu tree for role permission assignment."""

    return await svc.list_menu_tree_for_role_assignment(session)


@router.get("/{role_id}", response_model=SysRoleDetailOut)
async def get_role(
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> SysRoleDetailOut:
    """Return one role with menu ids."""

    row, menu_ids = await svc.get_role_detail(
        session, workspace_id=workspace_id, role_id=role_id
    )
    return SysRoleDetailOut(
        **_to_list_item(row).model_dump(),
        menu_ids=menu_ids,
    )


@router.post("", response_model=SysRoleDetailOut, status_code=201)
async def create_role(
    workspace_id: uuid.UUID,
    body: SysRoleCreateIn,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> SysRoleDetailOut:
    """Create a role in the current workspace."""

    row = await svc.create_role(
        session, workspace_id=workspace_id, data=_create_payload(body)
    )
    _, menu_ids = await svc.get_role_detail(
        session, workspace_id=workspace_id, role_id=row.id
    )
    return SysRoleDetailOut(
        **_to_list_item(row).model_dump(),
        menu_ids=menu_ids,
    )


@router.patch("/{role_id}", response_model=SysRoleDetailOut)
async def patch_role(
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    body: SysRolePatchIn,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> SysRoleDetailOut:
    """Partially update a workspace role."""

    row = await svc.update_role(
        session,
        workspace_id=workspace_id,
        role_id=role_id,
        patch=_patch_payload(body),
    )
    _, menu_ids = await svc.get_role_detail(
        session, workspace_id=workspace_id, role_id=row.id
    )
    return SysRoleDetailOut(
        **_to_list_item(row).model_dump(),
        menu_ids=menu_ids,
    )


@router.delete("/{role_id}", status_code=204)
async def delete_role(
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> Response:
    """Delete a role and its menu links."""

    await svc.delete_role(session, workspace_id=workspace_id, role_id=role_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
