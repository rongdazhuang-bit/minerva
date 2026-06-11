"""CRUD routes for workspace member user management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import (
    get_current_user,
    require_workspace_member,
)
from app.core.domain.identity.models import MembershipRole, User
from app.core.domain.identity.services import is_super_admin_user
from app.dependencies import get_db
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.dict.api.schemas import SysDictItemNodeOut
from app.sys.user.api.deps import (
    require_create_workspace_scope,
    require_workspace_manager_or_super_admin,
)
from app.sys.user.api.schemas import (
    SysRoleMetaOut,
    SysTenantMetaOut,
    SysUserCapabilitiesOut,
    SysUserCreateIn,
    SysUserListItemOut,
    SysUserListPageOut,
    SysUserPatchIn,
    SysWorkspaceMetaOut,
)
from app.sys.user.service import user_service as svc

router = APIRouter(prefix="/workspaces/{workspace_id}/users", tags=["users"])


def _parse_membership_role(value: str | None) -> MembershipRole | None:
    """Parse query membership role or return None."""

    if value is None or value.strip() == "":
        return None
    return MembershipRole(value.strip())


@router.get("", response_model=SysUserListPageOut)
async def list_users(
    workspace_id: uuid.UUID,
    email: str | None = Query(default=None),
    nickname: str | None = Query(default=None),
    phone: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    membership_role: str | None = Query(default=None),
    role_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysUserListPageOut:
    """List workspace members with optional filters."""

    actor_is_super = await is_super_admin_user(session, user_id=actor.id)
    items, total = await svc.list_users_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        actor_is_super_admin=actor_is_super,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=_parse_membership_role(membership_role),
        role_id=role_id,
    )
    return SysUserListPageOut(
        items=[SysUserListItemOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/meta/departments", response_model=list[SysDictItemNodeOut])
async def list_department_meta(
    workspace_id: uuid.UUID,
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[SysDictItemNodeOut]:
    """Return SYS_DEPARTMENT tree for user form."""

    return await svc.list_department_tree(session)


@router.get("/meta/roles", response_model=list[SysRoleMetaOut])
async def list_roles_meta(
    workspace_id: uuid.UUID,
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[SysRoleMetaOut]:
    """Return active workspace roles for assignment."""

    rows = await svc.list_assignable_roles(session, workspace_id=workspace_id)
    return [SysRoleMetaOut.model_validate(r) for r in rows]


@router.get("/meta/capabilities", response_model=SysUserCapabilitiesOut)
async def get_user_capabilities(
    workspace_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysUserCapabilitiesOut:
    """Return form capability flags for the current actor."""

    data = await svc.get_actor_capabilities(
        session, workspace_id=workspace_id, actor_user_id=actor.id
    )
    return SysUserCapabilitiesOut.model_validate(data)


@router.get("/meta/tenants", response_model=list[SysTenantMetaOut])
async def list_tenant_meta_for_user_form(
    workspace_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[SysTenantMetaOut]:
    """Return active sys_tenant rows for super-admin user create form."""

    rows = await svc.list_tenant_meta_for_user_form(
        session, actor_user_id=actor.id
    )
    return [SysTenantMetaOut.model_validate(row) for row in rows]


@router.get(
    "/meta/tenants/{tenant_id}/workspaces",
    response_model=list[SysWorkspaceMetaOut],
)
async def list_workspace_meta_for_user_form(
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[SysWorkspaceMetaOut]:
    """Return active sys_workspaces rows under one tenant."""

    rows = await svc.list_workspace_meta_for_user_form(
        session, actor_user_id=actor.id, tenant_id=tenant_id
    )
    return [SysWorkspaceMetaOut.model_validate(row) for row in rows]


@router.get("/{user_id}", response_model=SysUserListItemOut)
async def get_user(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysUserListItemOut:
    """Return one workspace member detail."""

    actor_is_super = await is_super_admin_user(session, user_id=actor.id)
    data = await svc.get_user_detail(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        actor_is_super_admin=actor_is_super,
    )
    return SysUserListItemOut.model_validate(data)


@router.post("", response_model=SysUserListItemOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    workspace_id: uuid.UUID,
    body: SysUserCreateIn,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_create_workspace_scope),
    session: AsyncSession = Depends(get_db),
) -> SysUserListItemOut:
    """Create a user and add them to the workspace."""

    data = await svc.create_user(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor.id,
        email=str(body.email),
        password=body.password,
        nickname=body.nickname,
        phone=body.phone,
        status=body.status,
        remark=body.remark,
        membership_role=MembershipRole(body.membership_role),
        department_item_id=body.department_item_id,
        role_ids=body.role_ids,
    )
    return SysUserListItemOut.model_validate(data)


@router.patch("/{user_id}", response_model=SysUserListItemOut)
async def patch_user(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    body: SysUserPatchIn,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_manager_or_super_admin),
    session: AsyncSession = Depends(get_db),
) -> SysUserListItemOut:
    """Update workspace member profile and roles."""

    patch = body.model_dump(exclude_unset=True)
    actor_is_super = await is_super_admin_user(session, user_id=actor.id)
    membership_role = None
    if "membership_role" in patch:
        membership_role = MembershipRole(patch["membership_role"])
    role_ids = patch.get("role_ids")
    update_department = "department_item_id" in patch
    department_item_id = patch.get("department_item_id")
    update_phone = "phone" in patch
    update_remark = "remark" in patch
    data = await svc.update_user(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        actor_user_id=actor.id,
        actor_is_super_admin=actor_is_super,
        nickname=patch.get("nickname"),
        status=patch.get("status"),
        password=patch.get("password"),
        membership_role=membership_role,
        department_item_id=department_item_id,
        update_department=update_department,
        phone=patch.get("phone"),
        update_phone=update_phone,
        remark=patch.get("remark"),
        update_remark=update_remark,
        role_ids=role_ids,
    )
    return SysUserListItemOut.model_validate(data)


@router.delete("/{user_id}/membership", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_membership(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_manager_or_super_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a user from the workspace."""

    await svc.remove_membership(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        actor_user_id=actor.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_account(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_manager_or_super_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Hard-delete a user account when permitted."""

    await svc.delete_user_account(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        actor_user_id=actor.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
