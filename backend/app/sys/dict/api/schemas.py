"""Pydantic contracts for system dictionaries and hierarchical items."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SysDictItemNodeOut(BaseModel):
    """Recursive dictionary item node (multi-level `parent_uuid` tree)."""

    id: uuid.UUID
    dict_uuid: uuid.UUID
    parent_uuid: uuid.UUID | None
    code: str
    name: str
    item_sort: int | None
    create_at: datetime | None
    update_at: datetime | None
    children: list["SysDictItemNodeOut"] = Field(default_factory=list)


class SysDictCreateIn(BaseModel):
    dict_code: str = Field(min_length=1, max_length=64)
    dict_name: str | None = Field(default=None, max_length=128)
    dict_sort: int | None = Field(default=None, ge=-32768, le=32767)


class SysDictPatchIn(BaseModel):
    dict_code: str | None = Field(default=None, min_length=1, max_length=64)
    dict_name: str | None = Field(default=None, max_length=128)
    dict_sort: int | None = Field(default=None, ge=-32768, le=32767)


class SysDictListItemOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    dict_code: str
    dict_name: str | None
    dict_sort: int | None
    create_at: datetime | None
    update_at: datetime | None
    item_tree: list[SysDictItemNodeOut] | None = None


class SysDictListPageOut(BaseModel):
    items: list[SysDictListItemOut]
    total: int


class SysDictItemCreateIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    item_sort: int | None = Field(default=None, ge=-32768, le=32767)
    parent_uuid: uuid.UUID | None = None


class SysDictItemPatchIn(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    item_sort: int | None = Field(default=None, ge=-32768, le=32767)
    parent_uuid: uuid.UUID | None = None


class SysDictItemOut(BaseModel):
    id: uuid.UUID
    dict_uuid: uuid.UUID
    parent_uuid: uuid.UUID | None
    code: str
    name: str
    item_sort: int | None
    create_at: datetime | None
    update_at: datetime | None


SysDictItemNodeOut.model_rebuild()
