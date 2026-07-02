"""Pydantic schemas for tenant-scoped role APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SysRoleCreateIn(BaseModel):
    """Body for creating a role under a tenant workspace."""

    workspace_id: uuid.UUID
    role_name: str = Field(min_length=1, max_length=64)
    role_key: str = Field(min_length=1, max_length=64)
    role_sort: int = 0
    status: bool = True
    remark: str | None = Field(default=None, max_length=500)
    menu_ids: list[uuid.UUID] = Field(default_factory=list)


class SysRolePatchIn(BaseModel):
    """Partial update body for a workspace role."""

    role_name: str | None = Field(default=None, min_length=1, max_length=64)
    role_key: str | None = Field(default=None, min_length=1, max_length=64)
    role_sort: int | None = None
    status: bool | None = None
    remark: str | None = Field(default=None, max_length=500)
    menu_ids: list[uuid.UUID] | None = None


class SysRoleListItemOut(BaseModel):
    """List-row projection for a workspace role with tenant/workspace labels."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str
    workspace_id: uuid.UUID
    workspace_name: str
    role_name: str
    role_key: str
    role_sort: int
    status: bool
    remark: str | None
    create_at: datetime | None = None
    update_at: datetime | None = None


class SysRoleDetailOut(SysRoleListItemOut):
    """Role detail including assigned menu ids."""

    menu_ids: list[uuid.UUID] = Field(default_factory=list)


class SysRoleListPageOut(BaseModel):
    """Paginated list payload for roles."""

    items: list[SysRoleListItemOut]
    total: int
    page: int
    page_size: int


class SysRoleCapabilitiesOut(BaseModel):
    """Frontend flags for role list filters and create-form scope pickers."""

    is_super_admin: bool
    is_tenant_admin: bool
    can_pick_tenant: bool
    can_pick_workspace: bool
    fixed_tenant_id: uuid.UUID | None = None
    fixed_tenant_name: str | None = None
    default_filter_tenant_id: uuid.UUID | None = None
    default_filter_workspace_id: uuid.UUID | None = None
