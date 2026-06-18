"""Persistence helpers for workspace MCP client and server rows."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.domain.db.models import SysMcpClient, SysMcpServer


async def list_clients_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysMcpClient]:
    """Return MCP client rows for one workspace, newest first."""

    result = await session.execute(
        select(SysMcpClient)
        .where(SysMcpClient.workspace_id == workspace_id)
        .order_by(SysMcpClient.create_at.desc(), SysMcpClient.id.desc())
    )
    return result.scalars().all()


async def get_client_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> SysMcpClient | None:
    """Fetch one MCP client row scoped to a workspace."""

    result = await session.execute(
        select(SysMcpClient).where(
            SysMcpClient.id == client_id,
            SysMcpClient.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def get_client_by_name_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
) -> SysMcpClient | None:
    """Fetch one MCP client by display name within a workspace."""

    result = await session.execute(
        select(SysMcpClient).where(
            SysMcpClient.workspace_id == workspace_id,
            SysMcpClient.name == name.strip(),
        )
    )
    return result.scalar_one_or_none()


async def list_enabled_clients_all_workspaces(
    session: AsyncSession,
) -> Sequence[SysMcpClient]:
    """Return all enabled MCP client rows for Registry warm-up."""

    result = await session.execute(
        select(SysMcpClient)
        .where(SysMcpClient.enabled.is_(True))
        .order_by(SysMcpClient.workspace_id, SysMcpClient.name)
    )
    return result.scalars().all()


async def delete_clients_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> int:
    """Delete all MCP client rows for a workspace; returns affected row count."""

    result = await session.execute(
        delete(SysMcpClient).where(SysMcpClient.workspace_id == workspace_id)
    )
    return int(result.rowcount or 0)


async def list_servers_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysMcpServer]:
    """Return MCP server rows for one workspace, newest first."""

    result = await session.execute(
        select(SysMcpServer)
        .where(SysMcpServer.workspace_id == workspace_id)
        .order_by(SysMcpServer.create_at.desc(), SysMcpServer.id.desc())
    )
    return result.scalars().all()


async def get_server_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    server_id: uuid.UUID,
) -> SysMcpServer | None:
    """Fetch one MCP server row scoped to a workspace."""

    result = await session.execute(
        select(SysMcpServer).where(
            SysMcpServer.id == server_id,
            SysMcpServer.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def get_server_by_slug(
    session: AsyncSession, *, slug: str
) -> SysMcpServer | None:
    """Fetch one MCP server row by globally unique slug."""

    result = await session.execute(
        select(SysMcpServer).where(SysMcpServer.slug == slug.strip())
    )
    return result.scalar_one_or_none()


async def list_enabled_servers_all_workspaces(
    session: AsyncSession,
) -> Sequence[SysMcpServer]:
    """Return all enabled MCP server rows for Registry warm-up."""

    result = await session.execute(
        select(SysMcpServer)
        .where(SysMcpServer.enabled.is_(True))
        .order_by(SysMcpServer.slug)
    )
    return result.scalars().all()


async def count_servers_referencing_client(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> int:
    """Count server rows in the workspace whose exposure JSON references client_id."""

    client_id_str = str(client_id)
    rows = await list_servers_for_workspace(session, workspace_id=workspace_id)
    count = 0
    for row in rows:
        exposure = row.exposure if isinstance(row.exposure, dict) else {}
        if exposure.get("include_all_clients"):
            count += 1
            continue
        raw_ids = exposure.get("mcp_client_ids")
        if not isinstance(raw_ids, list):
            continue
        if client_id_str in {str(item) for item in raw_ids}:
            count += 1
    return count


async def delete_servers_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> int:
    """Delete all MCP server rows for a workspace; returns affected row count."""

    result = await session.execute(
        delete(SysMcpServer).where(SysMcpServer.workspace_id == workspace_id)
    )
    return int(result.rowcount or 0)


async def count_clients_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> int:
    """Return total MCP client row count for a workspace."""

    result = await session.execute(
        select(func.count())
        .select_from(SysMcpClient)
        .where(SysMcpClient.workspace_id == workspace_id)
    )
    return int(result.scalar_one())
