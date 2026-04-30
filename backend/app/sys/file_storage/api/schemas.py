"""Pydantic contracts for file storage CRUD APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileStorageCreateIn(BaseModel):
    """Input payload for creating file storage configuration."""

    name: str | None = Field(default=None, max_length=32)
    type: str | None = Field(default=None, max_length=16)
    enabled: bool = True
    auth_type: str = Field(min_length=1, max_length=64)
    endpoint_url: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=128)
    auth_name: str | None = Field(default=None, max_length=64)
    auth_passwd: str | None = Field(default=None, max_length=128)


class FileStoragePatchIn(BaseModel):
    """Partial payload for patching file storage configuration."""

    name: str | None = Field(default=None, max_length=32)
    type: str | None = Field(default=None, max_length=16)
    enabled: bool | None = None
    auth_type: str | None = Field(default=None, min_length=1, max_length=64)
    endpoint_url: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=128)
    auth_name: str | None = Field(default=None, max_length=64)
    auth_passwd: str | None = Field(default=None, max_length=128)


class FileStorageListItemOut(BaseModel):
    """List-row projection for file storage table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str | None
    type: str | None
    enabled: bool
    auth_type: str
    endpoint_url: str | None
    auth_name: str | None
    has_api_key: bool
    has_password: bool
    create_at: datetime | None
    update_at: datetime | None


class FileStorageDetailOut(BaseModel):
    """Full detail payload including credential raw values."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str | None
    type: str | None
    enabled: bool
    auth_type: str
    endpoint_url: str | None
    api_key: str | None
    auth_name: str | None
    auth_passwd: str | None
    create_at: datetime | None
    update_at: datetime | None


class FileStorageListPageOut(BaseModel):
    """Paginated payload for file storage list endpoints."""

    items: list[FileStorageListItemOut]
    total: int
