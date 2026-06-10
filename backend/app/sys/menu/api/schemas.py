"""Pydantic schemas for sys_menu API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SysMenuNodeOut(BaseModel):
    """Nested menu node returned by list and nav endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    menu_name: str
    i18n_key: str | None = None
    menu_key: str | None = None
    order_num: int
    path: str | None = None
    menu_type: str
    perms: str | None = None
    icon: str | None = None
    visible: bool
    status: bool
    is_external: bool
    remark: str | None = None
    create_at: datetime | None = None
    update_at: datetime | None = None
    children: list[SysMenuNodeOut] = Field(default_factory=list)


class SysMenuOut(BaseModel):
    """Flat menu row for create/patch responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    menu_name: str
    i18n_key: str | None = None
    menu_key: str | None = None
    order_num: int
    path: str | None = None
    menu_type: str
    perms: str | None = None
    icon: str | None = None
    visible: bool
    status: bool
    is_external: bool
    remark: str | None = None
    create_at: datetime | None = None
    update_at: datetime | None = None


class SysMenuCreateIn(BaseModel):
    """Body for creating a menu row."""

    parent_id: uuid.UUID | None = None
    menu_name: str
    i18n_key: str | None = None
    menu_key: str | None = None
    order_num: int = 0
    path: str | None = None
    menu_type: str
    perms: str | None = None
    icon: str | None = None
    visible: bool = True
    status: bool = True
    is_external: bool = False
    remark: str | None = None


class SysMenuPatchIn(BaseModel):
    """Partial update body for a menu row."""

    parent_id: uuid.UUID | None = None
    menu_name: str | None = None
    i18n_key: str | None = None
    menu_key: str | None = None
    order_num: int | None = None
    path: str | None = None
    menu_type: str | None = None
    perms: str | None = None
    icon: str | None = None
    visible: bool | None = None
    status: bool | None = None
    is_external: bool | None = None
    remark: str | None = None


class MenuDeleteOut(BaseModel):
    """Response after cascade delete."""

    deleted_count: int
