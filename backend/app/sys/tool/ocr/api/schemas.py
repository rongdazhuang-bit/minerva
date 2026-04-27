from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OcrToolCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=128)
    auth_type: str | None = Field(default=None, max_length=64)
    user_name: str | None = Field(default=None, max_length=64)
    user_passwd: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=128)
    remark: str | None = Field(default=None, max_length=128)


class OcrToolPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    url: str | None = Field(default=None, min_length=1, max_length=128)
    auth_type: str | None = Field(default=None, max_length=64)
    user_name: str | None = Field(default=None, max_length=64)
    user_passwd: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=128)
    remark: str | None = Field(default=None, max_length=128)


class OcrToolListItemOut(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    auth_type: str | None
    user_name: str | None
    remark: str | None
    has_api_key: bool
    has_password: bool
    create_at: datetime | None
    update_at: datetime | None


class OcrToolDetailOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    url: str
    auth_type: str | None
    user_name: str | None
    user_passwd: str | None
    api_key: str | None
    remark: str | None
    create_at: datetime | None
    update_at: datetime | None
