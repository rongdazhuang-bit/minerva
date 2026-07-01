"""Pydantic schemas for platform tenant management APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SysTenantCreateIn(BaseModel):
    """Body for creating a tenant."""

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=64)
    status: bool = True
    remark: str | None = Field(default=None, max_length=500)


class SysTenantPatchIn(BaseModel):
    """Partial update body for a tenant."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    status: bool | None = None
    remark: str | None = Field(default=None, max_length=500)


class SysTenantOut(BaseModel):
    """Tenant projection for list and detail responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: bool
    remark: str | None
    create_at: datetime | None = None
    update_at: datetime | None = None


class SysTenantListPageOut(BaseModel):
    """Paginated list payload for tenants."""

    items: list[SysTenantOut]
    total: int
    page: int
    page_size: int


class SysWorkspaceCreateIn(BaseModel):
    """Body for creating a workspace under a tenant."""

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=64)
    status: bool = True
    remark: str | None = Field(default=None, max_length=500)


class SysWorkspacePatchIn(BaseModel):
    """Partial update body for a workspace."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    status: bool | None = None
    remark: str | None = Field(default=None, max_length=500)


class SysWorkspaceOut(BaseModel):
    """Workspace projection for list and detail responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    slug: str
    status: bool
    remark: str | None
    create_at: datetime | None = None
    update_at: datetime | None = None


class SysWorkspaceListPageOut(BaseModel):
    """Paginated list payload for workspaces."""

    items: list[SysWorkspaceOut]
    total: int
    page: int
    page_size: int


class SysTenantEntitlementsOut(BaseModel):
    """Enabled feature codes for one tenant."""

    feature_codes: list[str]


class SysTenantEntitlementsPutIn(BaseModel):
    """Replace tenant feature entitlements."""

    feature_codes: list[str]


class SysTenantAdminsOut(BaseModel):
    """Tenant administrator user ids."""

    user_ids: list[uuid.UUID]


class SysTenantAdminsPutIn(BaseModel):
    """Replace tenant administrator grants."""

    user_ids: list[uuid.UUID]


class SysUserGrantOut(BaseModel):
    """One user authorization grant within a tenant."""

    id: uuid.UUID
    user_id: uuid.UUID
    grant_type: str
    role_id: uuid.UUID | None = None
    permission_id: uuid.UUID | None = None
    scope_type: str
    scope_id: uuid.UUID | None = None
    status: bool
    create_at: datetime | None = None
    update_at: datetime | None = None


class SysUserGrantListPageOut(BaseModel):
    """Paginated grant list for a tenant."""

    items: list[SysUserGrantOut]
    total: int
    page: int
    page_size: int


class SysUserGrantCreateIn(BaseModel):
    """Body for creating a role or direct_permission grant."""

    user_id: uuid.UUID
    grant_type: str = Field(pattern=r"^(role|direct_permission)$")
    role_id: uuid.UUID | None = None
    permission_id: uuid.UUID | None = None
    scope_type: str = Field(pattern=r"^(tenant|workspace)$")
    scope_id: uuid.UUID | None = None
