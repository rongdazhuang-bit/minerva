"""Request/response schemas for MCP client and server CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class McpClientCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    transport: Literal["STDIO", "SSE", "STREAMABLE_HTTP"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    remark: str | None = Field(default=None, max_length=256)


class McpClientPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    transport: Literal["STDIO", "SSE", "STREAMABLE_HTTP"] | None = None
    config: dict[str, Any] | None = None
    secrets: dict[str, Any] | None = None
    enabled: bool | None = None
    remark: str | None = Field(default=None, max_length=256)


class McpClientListItemOut(BaseModel):
    id: uuid.UUID
    name: str
    transport: str
    enabled: bool
    remark: str | None
    last_test_at: datetime | None
    last_test_ok: bool | None
    has_secrets: bool
    create_at: datetime | None
    update_at: datetime | None


class McpClientDetailOut(McpClientListItemOut):
    workspace_id: uuid.UUID
    config: dict[str, Any]
    secrets: dict[str, Any]


class McpClientTestIn(BaseModel):
    transport: Literal["STDIO", "SSE", "STREAMABLE_HTTP"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)


class McpClientTestOut(BaseModel):
    ok: bool
    tool_names: list[str]
    error_code: str | None = None
    error_message: str | None = None


class McpServerCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64)
    exposure: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    auth_type: Literal["NONE", "BEARER", "API_KEY"] = "NONE"
    auth_secret: str | None = Field(default=None, max_length=512)
    remark: str | None = Field(default=None, max_length=256)


class McpServerPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    exposure: dict[str, Any] | None = None
    enabled: bool | None = None
    auth_type: Literal["NONE", "BEARER", "API_KEY"] | None = None
    auth_secret: str | None = Field(default=None, max_length=512)
    remark: str | None = Field(default=None, max_length=256)


class McpServerListItemOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    enabled: bool
    auth_type: str
    has_auth_secret: bool
    exposure: dict[str, Any]
    remark: str | None
    create_at: datetime | None
    update_at: datetime | None


class McpServerDetailOut(McpServerListItemOut):
    workspace_id: uuid.UUID
    auth_secret: str | None


class McpRuntimeStatusOut(BaseModel):
    client_enabled: bool
    server_enabled: bool
