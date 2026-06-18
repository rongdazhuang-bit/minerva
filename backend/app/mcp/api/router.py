"""Workspace MCP client/server management routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api.deps import (
    get_current_user,
    require_workspace_member,
    require_workspace_owner_or_admin,
)
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.mcp.api.schemas import (
    McpClientCreateIn,
    McpClientDetailOut,
    McpClientListItemOut,
    McpClientPatchIn,
    McpClientTestIn,
    McpClientTestOut,
    McpRuntimeStatusOut,
    McpServerCreateIn,
    McpServerDetailOut,
    McpServerListItemOut,
    McpServerPatchIn,
)
from app.mcp.domain.db.models import SysMcpClient, SysMcpServer
from app.mcp.service import mcp_client_service as client_svc
from app.mcp.service import mcp_server_service as server_svc

router = APIRouter(prefix="/workspaces/{workspace_id}/mcp", tags=["mcp"])


def _client_list_item(row: SysMcpClient) -> McpClientListItemOut:
    secrets = row.secrets if isinstance(row.secrets, dict) else {}
    return McpClientListItemOut(
        id=row.id,
        name=row.name,
        transport=row.transport,
        enabled=row.enabled,
        remark=row.remark,
        last_test_at=row.last_test_at,
        last_test_ok=row.last_test_ok,
        has_secrets=bool(secrets),
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _client_detail(row: SysMcpClient, *, redact_secrets: bool) -> McpClientDetailOut:
    secrets = row.secrets if isinstance(row.secrets, dict) else {}
    redacted = {} if redact_secrets else dict(secrets)
    if redact_secrets and secrets:
        redacted = {"_redacted": True}
    return McpClientDetailOut(
        **_client_list_item(row).model_dump(),
        workspace_id=row.workspace_id,
        config=dict(row.config or {}),
        secrets=redacted,
    )


def _server_list_item(row: SysMcpServer) -> McpServerListItemOut:
    return McpServerListItemOut(
        id=row.id,
        name=row.name,
        slug=row.slug,
        enabled=row.enabled,
        auth_type=row.auth_type,
        has_auth_secret=bool(row.auth_secret),
        exposure=dict(row.exposure or {}),
        remark=row.remark,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _server_detail(row: SysMcpServer) -> McpServerDetailOut:
    return McpServerDetailOut(
        **_server_list_item(row).model_dump(),
        workspace_id=row.workspace_id,
        auth_secret=row.auth_secret,
    )


@router.get("/runtime-status", response_model=McpRuntimeStatusOut)
async def get_runtime_status(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> McpRuntimeStatusOut:
    return McpRuntimeStatusOut(
        client_enabled=settings.mcp_client_enabled,
        server_enabled=settings.mcp_server_enabled,
    )


@router.get("/clients", response_model=list[McpClientListItemOut])
async def list_mcp_clients(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[McpClientListItemOut]:
    rows = await client_svc.list_clients(session, workspace_id=workspace_id)
    return [_client_list_item(row) for row in rows]


@router.get("/clients/{client_id}", response_model=McpClientDetailOut)
async def get_mcp_client(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> McpClientDetailOut:
    row = await client_svc.get_client(
        session, workspace_id=workspace_id, client_id=client_id
    )
    return _client_detail(row, redact_secrets=True)


@router.post("/clients/test", response_model=McpClientTestOut)
async def test_mcp_client(
    workspace_id: uuid.UUID,
    body: McpClientTestIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
) -> McpClientTestOut:
    result = await client_svc.test_client_connection(
        transport=body.transport,
        config=body.config,
        secrets=body.secrets,
    )
    return McpClientTestOut(
        ok=result.ok,
        tool_names=result.tool_names,
        error_code=result.error_code,
        error_message=result.error_message,
    )


@router.post("/clients", response_model=McpClientDetailOut, status_code=status.HTTP_201_CREATED)
async def create_mcp_client(
    workspace_id: uuid.UUID,
    body: McpClientCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> McpClientDetailOut:
    row = await client_svc.create_client(
        session,
        workspace_id=workspace_id,
        name=body.name,
        transport=body.transport,
        config=body.config,
        secrets=body.secrets,
        enabled=body.enabled,
        remark=body.remark,
    )
    return _client_detail(row, redact_secrets=False)


@router.patch("/clients/{client_id}", response_model=McpClientDetailOut)
async def patch_mcp_client(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    body: McpClientPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> McpClientDetailOut:
    row = await client_svc.update_client(
        session,
        workspace_id=workspace_id,
        client_id=client_id,
        name=body.name,
        transport=body.transport,
        config=body.config,
        secrets=body.secrets,
        enabled=body.enabled,
        remark=body.remark,
    )
    return _client_detail(row, redact_secrets=False)


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_mcp_client(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await client_svc.delete_client(
        session, workspace_id=workspace_id, client_id=client_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/servers", response_model=list[McpServerListItemOut])
async def list_mcp_servers(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[McpServerListItemOut]:
    rows = await server_svc.list_servers(session, workspace_id=workspace_id)
    return [_server_list_item(row) for row in rows]


@router.get("/servers/{server_id}", response_model=McpServerDetailOut)
async def get_mcp_server(
    workspace_id: uuid.UUID,
    server_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> McpServerDetailOut:
    row = await server_svc.get_server(
        session, workspace_id=workspace_id, server_id=server_id
    )
    detail = _server_detail(row)
    if detail.auth_secret:
        detail = detail.model_copy(update={"auth_secret": "***"})
    return detail


@router.post("/servers", response_model=McpServerDetailOut, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    workspace_id: uuid.UUID,
    body: McpServerCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> McpServerDetailOut:
    row = await server_svc.create_server(
        session,
        workspace_id=workspace_id,
        name=body.name,
        slug=body.slug,
        exposure=body.exposure,
        enabled=body.enabled,
        auth_type=body.auth_type,
        auth_secret=body.auth_secret,
        remark=body.remark,
    )
    return _server_detail(row)


@router.patch("/servers/{server_id}", response_model=McpServerDetailOut)
async def patch_mcp_server(
    workspace_id: uuid.UUID,
    server_id: uuid.UUID,
    body: McpServerPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> McpServerDetailOut:
    row = await server_svc.update_server(
        session,
        workspace_id=workspace_id,
        server_id=server_id,
        name=body.name,
        slug=body.slug,
        exposure=body.exposure,
        enabled=body.enabled,
        auth_type=body.auth_type,
        auth_secret=body.auth_secret,
        remark=body.remark,
    )
    return _server_detail(row)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_mcp_server(
    workspace_id: uuid.UUID,
    server_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await server_svc.delete_server(
        session, workspace_id=workspace_id, server_id=server_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
