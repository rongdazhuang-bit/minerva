"""Pydantic schemas for sys_permission list API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SysPermissionOut(BaseModel):
    """One row from the global permission catalog."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    perm_code: str
    perm_name: str
    perm_type: str
    resource_pattern: str | None
    menu_id: uuid.UUID | None
    status: bool
    remark: str | None
    create_at: datetime | None
    update_at: datetime | None


class SysPermissionListPageOut(BaseModel):
    """Paginated permission catalog response."""

    items: list[SysPermissionOut]
    total: int
    page: int
    page_size: int
