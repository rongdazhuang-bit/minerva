"""Pydantic schemas for workspace-scoped role APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SysRoleCreateIn(BaseModel):
    """Body for creating a workspace role."""

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
    """List-row projection for a workspace role."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
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
