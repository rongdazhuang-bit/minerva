"""Pydantic schemas for workspace user management API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

MembershipRoleLiteral = Literal["admin", "member"]


class SysUserCreateIn(BaseModel):
    """Body for creating a workspace member with a new global account."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    status: bool = True
    remark: str | None = Field(default=None, max_length=500)
    membership_role: MembershipRoleLiteral
    department_item_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class SysUserPatchIn(BaseModel):
    """Partial update for a workspace member."""

    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    status: bool | None = None
    remark: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    membership_role: MembershipRoleLiteral | None = None
    department_item_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] | None = None


class SysUserListItemOut(BaseModel):
    """One workspace member in list or detail responses."""

    id: uuid.UUID
    email: str
    nickname: str
    phone: str | None
    status: bool
    remark: str | None
    department_item_id: uuid.UUID | None
    department_name: str | None
    membership_role: str
    role_ids: list[uuid.UUID]
    role_names: list[str]
    tenant_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    tenant_name: str | None = None
    workspace_name: str | None = None
    created_at: datetime
    update_at: datetime | None
    can_hard_delete: bool


class SysUserListPageOut(BaseModel):
    """Paginated workspace members."""

    items: list[SysUserListItemOut]
    total: int
    page: int
    page_size: int


class SysRoleMetaOut(BaseModel):
    """Assignable role option for user form."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role_name: str
    role_key: str
    status: bool


class SysTenantMetaOut(BaseModel):
    """Tenant option for super-admin user create form (sys_tenant)."""

    id: uuid.UUID
    name: str
    slug: str


class SysWorkspaceMetaOut(BaseModel):
    """Workspace option under a tenant (sys_workspaces)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    slug: str


class SysUserCapabilitiesOut(BaseModel):
    """Actor permissions for the user form in a target workspace."""

    is_super_admin: bool
    actor_workspace_role: str | None
    can_edit_membership_role: bool
    can_view_membership_role: bool = False
    can_edit_tenant_admin: bool = False
    assignable_membership_roles: list[str]
    can_pick_tenant_workspace: bool
    is_tenant_admin: bool = False
    default_tenant_id: uuid.UUID | None = None
    can_pick_tenant: bool = False
    can_pick_workspace: bool = False
    fixed_tenant_id: uuid.UUID | None = None
    fixed_tenant_name: str | None = None


class SysUserListCapabilitiesOut(BaseModel):
    """Platform-level list/form scope capabilities from JWT context."""

    is_super_admin: bool
    is_tenant_admin: bool
    can_pick_tenant: bool
    can_pick_workspace: bool
    fixed_tenant_id: uuid.UUID | None = None
    fixed_tenant_name: str | None = None
    default_filter_tenant_id: uuid.UUID | None = None
    default_filter_workspace_id: uuid.UUID | None = None
    actor_workspace_role: str | None
    can_edit_membership_role: bool
    can_view_membership_role: bool = False
    can_edit_tenant_admin: bool = False
    assignable_membership_roles: list[str]
