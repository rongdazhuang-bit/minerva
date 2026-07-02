"""MCP client configuration use cases."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.mcp.api.schemas import McpCallToolOut, McpListResourcesOut, McpListToolsOut, McpReadResourceOut
from app.mcp.domain.db.models import SysMcpClient
from app.mcp.infrastructure import repository as mcp_repo
from app.mcp.runtime.client_explorer import (
    McpExplorerContext,
    call_tool_for_client,
    list_resources_for_client,
    list_tools_for_client,
    read_resource_for_client,
)
from app.mcp.runtime.connection_tester import McpConnectionTester, McpTestResult
from app.agent.infrastructure.skill_loader import invalidate_subagent_cache_for_workspace
from app.mcp.runtime.registry import mcp_registry

_VALID_TRANSPORTS = frozenset({"STDIO", "SSE", "STREAMABLE_HTTP"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_transport(value: str) -> str:
    key = (value or "").strip().upper()
    if key not in _VALID_TRANSPORTS:
        raise AppError(
            "mcp.invalid_transport",
            f"transport must be one of {', '.join(sorted(_VALID_TRANSPORTS))}",
            400,
        )
    return key


def _validate_client_payload(*, transport: str, config: dict[str, Any]) -> None:
    """Ensure required config keys exist for the selected transport."""

    if transport == "STDIO":
        if not str(config.get("command") or "").strip():
            raise AppError("mcp.invalid_config", "STDIO requires config.command", 400)
        return
    if not str(config.get("url") or "").strip():
        raise AppError("mcp.invalid_config", f"{transport} requires config.url", 400)


async def test_client_connection(
    *,
    transport: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> McpTestResult:
    """Probe external MCP server without persisting configuration."""

    transport_key = _normalize_transport(transport)
    payload = dict(config or {})
    secret_payload = dict(secrets or {})
    _validate_client_payload(transport=transport_key, config=payload)
    tester = McpConnectionTester()
    return await tester.test(
        transport=transport_key,
        config=payload,
        secrets=secret_payload,
    )


async def _require_successful_test(
    *,
    transport: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None,
) -> McpTestResult:
    """Run connectivity test and raise ``AppError`` when it fails."""

    result = await test_client_connection(
        transport=transport,
        config=config,
        secrets=secrets,
    )
    if not result.ok:
        raise AppError(
            result.error_code or "mcp.client_connect_failed",
            result.error_message or "MCP connection test failed",
            422,
        )
    return result


async def list_clients(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[SysMcpClient]:
    """List MCP client rows for a workspace."""

    return list(await mcp_repo.list_clients_for_workspace(session, workspace_id=workspace_id))


async def get_client(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> SysMcpClient:
    """Fetch one MCP client row or raise 404."""

    row = await mcp_repo.get_client_for_workspace(
        session,
        workspace_id=workspace_id,
        client_id=client_id,
    )
    if row is None:
        raise AppError("mcp.client_not_found", "MCP client not found", 404)
    return row


async def create_client(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    transport: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None = None,
    enabled: bool = True,
    remark: str | None = None,
    skip_test: bool = False,
) -> SysMcpClient:
    """Create MCP client after mandatory connectivity test (unless ``skip_test``)."""

    transport_key = _normalize_transport(transport)
    payload = dict(config or {})
    secret_payload = dict(secrets or {})
    _validate_client_payload(transport=transport_key, config=payload)
    trimmed_name = name.strip()
    if not trimmed_name:
        raise AppError("mcp.invalid_name", "name is required", 400)
    if await mcp_repo.get_client_by_name_for_workspace(
        session, workspace_id=workspace_id, name=trimmed_name
    ):
        raise AppError("mcp.client_name_duplicate", "MCP client name already exists", 409)

    test_result: McpTestResult | None = None
    if not skip_test:
        test_result = await _require_successful_test(
            transport=transport_key,
            config=payload,
            secrets=secret_payload,
        )

    now = _utc_now()
    row = SysMcpClient(
        workspace_id=workspace_id,
        name=trimmed_name,
        transport=transport_key,
        config=payload,
        secrets=secret_payload,
        enabled=enabled,
        remark=remark.strip() if remark else None,
        last_test_at=now if test_result else None,
        last_test_ok=True if test_result else None,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "mcp.client_name_duplicate", "MCP client name already exists", 409
        ) from exc
    await session.refresh(row)
    await mcp_registry.refresh_workspace_clients(session, workspace_id)
    invalidate_subagent_cache_for_workspace(workspace_id)
    return row


async def update_client(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    name: str | None = None,
    transport: str | None = None,
    config: dict[str, Any] | None = None,
    secrets: dict[str, Any] | None = None,
    enabled: bool | None = None,
    remark: str | None = None,
    skip_test: bool = False,
) -> SysMcpClient:
    """Update MCP client; re-test connectivity before commit unless ``skip_test``."""

    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    next_transport = _normalize_transport(transport or row.transport)
    next_config = dict(config if config is not None else row.config or {})
    next_secrets = dict(secrets if secrets is not None else row.secrets or {})
    _validate_client_payload(transport=next_transport, config=next_config)

    if name is not None:
        trimmed = name.strip()
        if not trimmed:
            raise AppError("mcp.invalid_name", "name is required", 400)
        existing = await mcp_repo.get_client_by_name_for_workspace(
            session, workspace_id=workspace_id, name=trimmed
        )
        if existing is not None and existing.id != row.id:
            raise AppError("mcp.client_name_duplicate", "MCP client name already exists", 409)
        row.name = trimmed

    row.transport = next_transport
    row.config = next_config
    row.secrets = next_secrets
    if enabled is not None:
        row.enabled = enabled
    if remark is not None:
        row.remark = remark.strip() or None

    test_result: McpTestResult | None = None
    if not skip_test:
        test_result = await _require_successful_test(
            transport=next_transport,
            config=next_config,
            secrets=next_secrets,
        )
        row.last_test_at = _utc_now()
        row.last_test_ok = True

    row.update_at = _utc_now()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "mcp.client_name_duplicate", "MCP client name already exists", 409
        ) from exc
    await session.refresh(row)
    await mcp_registry.refresh_workspace_clients(session, workspace_id)
    invalidate_subagent_cache_for_workspace(workspace_id)
    return row


async def delete_client(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> None:
    """Delete MCP client when not referenced by server exposure config."""

    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    refs = await mcp_repo.count_servers_referencing_client(
        session,
        workspace_id=workspace_id,
        client_id=client_id,
    )
    if refs > 0:
        raise AppError(
            "mcp.client_in_use",
            "MCP client is referenced by one or more server configs",
            409,
        )
    await session.delete(row)
    await session.commit()
    await mcp_registry.refresh_workspace_clients(session, workspace_id)
    invalidate_subagent_cache_for_workspace(workspace_id)


def _explorer_context_from_row(row: SysMcpClient) -> McpExplorerContext:
    """Build explorer context from a persisted client row."""

    return McpExplorerContext(
        transport=row.transport,
        config=dict(row.config or {}),
        secrets=dict(row.secrets or {}),
    )


async def list_client_tools(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> McpListToolsOut:
    """List MCP tools for one saved client configuration."""

    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    return await list_tools_for_client(_explorer_context_from_row(row))


async def call_client_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    tool_name: str,
    arguments: dict[str, Any],
) -> McpCallToolOut:
    """Call one MCP tool for a saved client configuration."""

    name = (tool_name or "").strip()
    if not name:
        raise AppError("mcp.invalid_tool_name", "tool_name is required", 400)
    if not isinstance(arguments, dict):
        raise AppError("mcp.invalid_arguments", "arguments must be a JSON object", 400)
    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    return await call_tool_for_client(
        _explorer_context_from_row(row),
        tool_name=name,
        arguments=arguments,
    )


async def list_client_resources(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> McpListResourcesOut:
    """List MCP resources for one saved client configuration."""

    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    return await list_resources_for_client(_explorer_context_from_row(row))


async def read_client_resource(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    uri: str,
) -> McpReadResourceOut:
    """Read one MCP resource for a saved client configuration."""

    target_uri = (uri or "").strip()
    if not target_uri:
        raise AppError("mcp.invalid_resource_uri", "uri is required", 400)
    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    return await read_resource_for_client(
        _explorer_context_from_row(row),
        uri=target_uri,
    )
