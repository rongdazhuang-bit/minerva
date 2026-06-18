"""In-memory MCP configuration registry (warm on startup, refresh on CRUD)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.mcp.infrastructure import repository as mcp_repo
from app.mcp.runtime.client_bridge import (
    close_mcp_client_bundles,
    load_langchain_tools_for_snapshots,
)
from app.mcp.runtime.snapshots import (
    McpClientSnapshot,
    McpServerSnapshot,
    client_row_to_snapshot,
    server_row_to_snapshot,
)

__all__ = [
    "McpClientSnapshot",
    "McpServerSnapshot",
    "McpRuntimeRegistry",
    "mcp_registry",
]


class McpRuntimeRegistry:
    """Singleton facade for warmed MCP client/server configuration."""

    _instance: McpRuntimeRegistry | None = None

    def __init__(self) -> None:
        self._clients: dict[uuid.UUID, list[McpClientSnapshot]] = {}
        self._servers: dict[uuid.UUID, list[McpServerSnapshot]] = {}

    @classmethod
    def get(cls) -> McpRuntimeRegistry:
        """Return the process-wide registry singleton."""

        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def warm_from_db(self, session: AsyncSession) -> None:
        """Load all enabled client/server rows into memory."""

        client_rows = await mcp_repo.list_enabled_clients_all_workspaces(session)
        server_rows = await mcp_repo.list_enabled_servers_all_workspaces(session)
        self._clients.clear()
        self._servers.clear()
        for row in client_rows:
            snap = client_row_to_snapshot(row)
            self._clients.setdefault(snap.workspace_id, []).append(snap)
        for row in server_rows:
            snap = server_row_to_snapshot(row)
            self._servers.setdefault(snap.workspace_id, []).append(snap)

    async def refresh_workspace_clients(
        self, session: AsyncSession, workspace_id: uuid.UUID
    ) -> None:
        """Reload enabled MCP client snapshots for one workspace."""

        rows = await mcp_repo.list_clients_for_workspace(session, workspace_id=workspace_id)
        snapshots = [client_row_to_snapshot(row) for row in rows if row.enabled]
        if snapshots:
            self._clients[workspace_id] = snapshots
        else:
            self._clients.pop(workspace_id, None)

    async def refresh_workspace_servers(
        self, session: AsyncSession, workspace_id: uuid.UUID
    ) -> None:
        """Reload enabled MCP server snapshots for one workspace."""

        rows = await mcp_repo.list_servers_for_workspace(session, workspace_id=workspace_id)
        snapshots = [server_row_to_snapshot(row) for row in rows if row.enabled]
        if snapshots:
            self._servers[workspace_id] = snapshots
        else:
            self._servers.pop(workspace_id, None)

    def list_client_snapshots(self, workspace_id: uuid.UUID) -> list[McpClientSnapshot]:
        """Return cached enabled client snapshots for a workspace."""

        return list(self._clients.get(workspace_id, []))

    def list_server_snapshots(self) -> list[McpServerSnapshot]:
        """Return all cached enabled server snapshots."""

        out: list[McpServerSnapshot] = []
        for rows in self._servers.values():
            out.extend(rows)
        return out

    async def resolve_langchain_tools(
        self, workspace_id: uuid.UUID
    ) -> tuple[list[Any], list[Any], list[str]]:
        """Open MCP client sessions for a workspace and return LangChain tools + bundles."""

        if not settings.mcp_client_enabled:
            return [], [], []
        snapshots = self.list_client_snapshots(workspace_id)
        if not snapshots:
            return [], [], []
        return await load_langchain_tools_for_snapshots(snapshots)

    @staticmethod
    async def close_tool_bundles(bundles: list[Any]) -> None:
        """Close MCP sessions opened during ``resolve_langchain_tools``."""

        await close_mcp_client_bundles(bundles)


mcp_registry = McpRuntimeRegistry.get()
