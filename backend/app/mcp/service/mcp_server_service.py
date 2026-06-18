"""MCP server exposure configuration use cases."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.skill_loader import list_indexed_skill_ids
from app.exceptions import AppError
from app.mcp.domain.db.models import SysMcpServer
from app.mcp.infrastructure import repository as mcp_repo
from app.mcp.runtime.registry import mcp_registry

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_VALID_AUTH = frozenset({"NONE", "BEARER", "API_KEY"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_slug(value: str) -> str:
    slug = (value or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise AppError(
            "mcp.invalid_slug",
            "slug must match ^[a-z0-9][a-z0-9-]{1,62}$",
            400,
        )
    return slug


def _normalize_auth_type(value: str) -> str:
    key = (value or "NONE").strip().upper()
    if key not in _VALID_AUTH:
        raise AppError(
            "mcp.invalid_auth_type",
            f"auth_type must be one of {', '.join(sorted(_VALID_AUTH))}",
            400,
        )
    return key


async def validate_exposure(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    exposure: dict[str, Any],
) -> dict[str, Any]:
    """Validate exposure JSON references existing skills and client rows."""

    payload = dict(exposure or {})
    allowed_skills = set(list_indexed_skill_ids())
    if payload.get("include_all_builtin"):
        payload.setdefault("builtin_skills", [])
    else:
        raw_skills = payload.get("builtin_skills")
        skills = [str(s).strip().lower() for s in raw_skills] if isinstance(raw_skills, list) else []
        for sid in skills:
            if sid not in allowed_skills:
                raise AppError("mcp.invalid_exposure", f"Unknown builtin skill: {sid}", 400)
        payload["builtin_skills"] = skills

    if payload.get("include_all_clients"):
        payload.setdefault("mcp_client_ids", [])
    else:
        raw_ids = payload.get("mcp_client_ids")
        ids: list[str] = []
        if isinstance(raw_ids, list):
            for item in raw_ids:
                try:
                    client_id = uuid.UUID(str(item))
                except ValueError as exc:
                    raise AppError("mcp.invalid_exposure", "Invalid mcp_client_ids entry", 400) from exc
                row = await mcp_repo.get_client_for_workspace(
                    session,
                    workspace_id=workspace_id,
                    client_id=client_id,
                )
                if row is None or not row.enabled:
                    raise AppError(
                        "mcp.invalid_exposure",
                        f"MCP client not found or disabled: {client_id}",
                        400,
                    )
                ids.append(str(client_id))
        payload["mcp_client_ids"] = ids
    return payload


async def list_servers(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[SysMcpServer]:
    """List MCP server rows for a workspace."""

    return list(await mcp_repo.list_servers_for_workspace(session, workspace_id=workspace_id))


async def get_server(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    server_id: uuid.UUID,
) -> SysMcpServer:
    """Fetch one MCP server row or raise 404."""

    row = await mcp_repo.get_server_for_workspace(
        session,
        workspace_id=workspace_id,
        server_id=server_id,
    )
    if row is None:
        raise AppError("mcp.server_not_found", "MCP server not found", 404)
    return row


async def create_server(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    slug: str,
    exposure: dict[str, Any],
    enabled: bool = True,
    auth_type: str = "NONE",
    auth_secret: str | None = None,
    remark: str | None = None,
) -> SysMcpServer:
    """Create MCP server exposure config (no external connectivity test)."""

    trimmed_name = name.strip()
    if not trimmed_name:
        raise AppError("mcp.invalid_name", "name is required", 400)
    slug_key = _normalize_slug(slug)
    auth_key = _normalize_auth_type(auth_type)
    exposure_payload = await validate_exposure(
        session, workspace_id=workspace_id, exposure=exposure
    )
    if await mcp_repo.get_server_by_slug(session, slug=slug_key):
        raise AppError("mcp.slug_duplicate", "MCP server slug already exists", 409)

    now = _utc_now()
    row = SysMcpServer(
        workspace_id=workspace_id,
        name=trimmed_name,
        slug=slug_key,
        enabled=enabled,
        exposure=exposure_payload,
        auth_type=auth_key,
        auth_secret=auth_secret.strip() if auth_secret else None,
        remark=remark.strip() if remark else None,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("mcp.slug_duplicate", "MCP server slug already exists", 409) from exc
    await session.refresh(row)
    await mcp_registry.refresh_workspace_servers(session, workspace_id)
    return row


async def update_server(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    server_id: uuid.UUID,
    name: str | None = None,
    slug: str | None = None,
    exposure: dict[str, Any] | None = None,
    enabled: bool | None = None,
    auth_type: str | None = None,
    auth_secret: str | None = None,
    remark: str | None = None,
) -> SysMcpServer:
    """Update MCP server config and refresh registry."""

    row = await get_server(session, workspace_id=workspace_id, server_id=server_id)
    if name is not None:
        trimmed = name.strip()
        if not trimmed:
            raise AppError("mcp.invalid_name", "name is required", 400)
        row.name = trimmed
    if slug is not None:
        slug_key = _normalize_slug(slug)
        existing = await mcp_repo.get_server_by_slug(session, slug=slug_key)
        if existing is not None and existing.id != row.id:
            raise AppError("mcp.slug_duplicate", "MCP server slug already exists", 409)
        row.slug = slug_key
    if exposure is not None:
        row.exposure = await validate_exposure(
            session, workspace_id=workspace_id, exposure=exposure
        )
    if enabled is not None:
        row.enabled = enabled
    if auth_type is not None:
        row.auth_type = _normalize_auth_type(auth_type)
    if auth_secret is not None:
        row.auth_secret = auth_secret.strip() or None
    if remark is not None:
        row.remark = remark.strip() or None
    row.update_at = _utc_now()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError("mcp.slug_duplicate", "MCP server slug already exists", 409) from exc
    await session.refresh(row)
    await mcp_registry.refresh_workspace_servers(session, workspace_id)
    return row


async def delete_server(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    server_id: uuid.UUID,
) -> None:
    """Delete one MCP server row."""

    row = await get_server(session, workspace_id=workspace_id, server_id=server_id)
    await session.delete(row)
    await session.commit()
    await mcp_registry.refresh_workspace_servers(session, workspace_id)
