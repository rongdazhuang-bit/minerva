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
    url: str | None = None
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


class McpToolAnnotationOut(BaseModel):
    readOnlyHint: bool = False
    destructiveHint: bool = False
    idempotentHint: bool = False
    openWorldHint: bool = False


class McpToolOut(BaseModel):
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    annotations: McpToolAnnotationOut = Field(default_factory=McpToolAnnotationOut)


class McpListToolsOut(BaseModel):
    ok: bool
    tools: list[McpToolOut] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class McpCallToolIn(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpCallToolOut(BaseModel):
    ok: bool
    content: list[dict[str, Any]] = Field(default_factory=list)
    structuredContent: dict[str, Any] | None = None
    isError: bool = False
    error_code: str | None = None
    error_message: str | None = None


class McpResourceOut(BaseModel):
    """One MCP resource entry from ``list_resources``."""

    uri: str
    name: str | None = None
    description: str | None = None
    mimeType: str | None = None


class McpListResourcesOut(BaseModel):
    """Result of listing MCP resources for one client."""

    ok: bool
    resources: list[McpResourceOut] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class McpReadResourceIn(BaseModel):
    """Body for reading one MCP resource by URI."""

    uri: str


class McpResourceContentOut(BaseModel):
    """One content block from ``read_resource``."""

    uri: str
    mimeType: str | None = None
    text: str | None = None
    blob: str | None = None


class McpReadResourceOut(BaseModel):
    """Result of reading one MCP resource."""

    ok: bool
    contents: list[McpResourceContentOut] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
