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
