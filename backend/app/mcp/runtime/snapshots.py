"""Immutable runtime snapshots for MCP registry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.mcp.domain.db.models import SysMcpClient, SysMcpServer


@dataclass(frozen=True)
class McpClientSnapshot:
    """Immutable MCP client config used at Agent run time."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    transport: str
    config: dict[str, Any]
    secrets: dict[str, Any]
    enabled: bool


@dataclass(frozen=True)
class McpServerSnapshot:
    """Immutable MCP server exposure config used for outbound routes."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    slug: str
    enabled: bool
    exposure: dict[str, Any]
    auth_type: str
    auth_secret: str | None


def client_row_to_snapshot(row: SysMcpClient) -> McpClientSnapshot:
    """Map ORM client row to a runtime snapshot."""

    return McpClientSnapshot(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        transport=row.transport,
        config=dict(row.config or {}),
        secrets=dict(row.secrets or {}),
        enabled=bool(row.enabled),
    )


def server_row_to_snapshot(row: SysMcpServer) -> McpServerSnapshot:
    """Map ORM server row to a runtime snapshot."""

    return McpServerSnapshot(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        slug=row.slug,
        enabled=bool(row.enabled),
        exposure=dict(row.exposure or {}),
        auth_type=row.auth_type,
        auth_secret=row.auth_secret,
    )
