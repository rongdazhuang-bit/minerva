"""Platform super-admin tenant and workspace management."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import Tenant, Workspace
from app.exceptions import AppError
from app.sys.tenant.infrastructure import repository as repo

_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")


def _utc_now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(UTC)


def validate_slug(slug: str, *, code_prefix: str = "tenant") -> str:
    """Normalize and validate slug; raise AppError on invalid format."""

    normalized = slug.strip().lower()
    if not _SLUG_RE.fullmatch(normalized):
        raise AppError(
            f"{code_prefix}.invalid_slug",
            "Invalid slug format",
            400,
        )
    return normalized


def _is_unique_violation(exc: IntegrityError) -> bool:
    """True when the DB error is a unique constraint violation."""

    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "pgcode", None) == "23505":
        return True
    return "unique" in str(exc).lower()


async def _commit_or_conflict(
    session: AsyncSession,
    *,
    code: str,
) -> None:
    """Commit or map unique violations to conflict error."""

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if _is_unique_violation(e):
            raise AppError(code, "Duplicate slug", 409) from e
        raise


async def _require_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> Tenant:
    """Load tenant or raise tenant.not_found."""

    row = await repo.get_tenant(session, tenant_id=tenant_id)
    if row is None:
        raise AppError("tenant.not_found", "Tenant not found", 404)
    return row


async def list_tenants_page(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    name: str | None = None,
    status: bool | None = None,
) -> tuple[list[Tenant], int]:
    """Return paginated tenants."""

    total = await repo.count_tenants_page(session, name=name, status=status)
    offset = (page - 1) * page_size
    rows = await repo.list_tenants_page(
        session, name=name, status=status, offset=offset, limit=page_size
    )
    return rows, total


async def get_tenant(session: AsyncSession, *, tenant_id: uuid.UUID) -> Tenant:
    """Return one tenant or raise tenant.not_found."""

    return await _require_tenant(session, tenant_id=tenant_id)


async def create_tenant(session: AsyncSession, payload: dict[str, Any]) -> Tenant:
    """Create a tenant row."""

    slug = validate_slug(str(payload["slug"]), code_prefix="tenant")
    row = Tenant(
        name=str(payload["name"]).strip(),
        slug=slug,
        status=bool(payload.get("status", True)),
        remark=payload.get("remark"),
    )
    session.add(row)
    await _commit_or_conflict(session, code="tenant.conflict")
    await session.refresh(row)
    return row


async def patch_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    payload: dict[str, Any],
) -> Tenant:
    """Partially update a tenant."""

    row = await _require_tenant(session, tenant_id=tenant_id)
    if "name" in payload and payload["name"] is not None:
        row.name = str(payload["name"]).strip()
    if "slug" in payload and payload["slug"] is not None:
        row.slug = validate_slug(str(payload["slug"]), code_prefix="tenant")
    if "status" in payload and payload["status"] is not None:
        row.status = bool(payload["status"])
    if "remark" in payload:
        row.remark = payload["remark"]
    row.update_at = _utc_now()
    await _commit_or_conflict(session, code="tenant.conflict")
    await session.refresh(row)
    return row


async def delete_tenant(session: AsyncSession, *, tenant_id: uuid.UUID) -> None:
    """Cascade-delete tenant and related membership/workspace rows."""

    await _require_tenant(session, tenant_id=tenant_id)
    await repo.delete_tenant_cascade(session, tenant_id=tenant_id)
    await session.commit()


async def list_workspaces_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    page: int,
    page_size: int,
    name: str | None = None,
    status: bool | None = None,
) -> tuple[list[Workspace], int]:
    """Return paginated workspaces under tenant."""

    await _require_tenant(session, tenant_id=tenant_id)
    total = await repo.count_workspaces_page(
        session, tenant_id=tenant_id, name=name, status=status
    )
    offset = (page - 1) * page_size
    rows = await repo.list_workspaces_page(
        session,
        tenant_id=tenant_id,
        name=name,
        status=status,
        offset=offset,
        limit=page_size,
    )
    return rows, total


async def get_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Workspace:
    """Return one workspace scoped to tenant or raise workspace.not_found."""

    await _require_tenant(session, tenant_id=tenant_id)
    row = await repo.get_workspace_for_tenant(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    if row is None:
        raise AppError("workspace.not_found", "Workspace not found", 404)
    return row


async def create_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    payload: dict[str, Any],
) -> Workspace:
    """Create workspace under tenant."""

    await _require_tenant(session, tenant_id=tenant_id)
    slug = validate_slug(str(payload["slug"]), code_prefix="workspace")
    row = Workspace(
        tenant_id=tenant_id,
        name=str(payload["name"]).strip(),
        slug=slug,
        status=bool(payload.get("status", True)),
        remark=payload.get("remark"),
    )
    session.add(row)
    await _commit_or_conflict(session, code="workspace.conflict")
    await session.refresh(row)
    return row


async def patch_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    payload: dict[str, Any],
) -> Workspace:
    """Partially update workspace scoped to tenant."""

    await _require_tenant(session, tenant_id=tenant_id)
    row = await repo.get_workspace_for_tenant(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    if row is None:
        raise AppError("workspace.not_found", "Workspace not found", 404)
    if "name" in payload and payload["name"] is not None:
        row.name = str(payload["name"]).strip()
    if "slug" in payload and payload["slug"] is not None:
        row.slug = validate_slug(str(payload["slug"]), code_prefix="workspace")
    if "status" in payload and payload["status"] is not None:
        row.status = bool(payload["status"])
    if "remark" in payload:
        row.remark = payload["remark"]
    row.update_at = _utc_now()
    await _commit_or_conflict(session, code="workspace.conflict")
    await session.refresh(row)
    return row


async def delete_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Delete only the workspace row."""

    await _require_tenant(session, tenant_id=tenant_id)
    affected = await repo.delete_workspace_row(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    if affected == 0:
        raise AppError("workspace.not_found", "Workspace not found", 404)
    await session.commit()
