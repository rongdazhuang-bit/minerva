"""CRUD routes for platform super-admin tenant and workspace management."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import Tenant, User, Workspace
from app.dependencies import get_db
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.tenant.api.deps import require_super_admin
from app.sys.tenant.api.schemas import (
    SysTenantCreateIn,
    SysTenantListPageOut,
    SysTenantOut,
    SysTenantPatchIn,
    SysWorkspaceCreateIn,
    SysWorkspaceListPageOut,
    SysWorkspaceOut,
    SysWorkspacePatchIn,
)
from app.sys.tenant.service import tenant_service as svc

router = APIRouter(prefix="/sys/tenants", tags=["tenants"])


def _tenant_out(row: Tenant) -> SysTenantOut:
    """Project tenant ORM row to response schema."""

    return SysTenantOut.model_validate(row)


def _workspace_out(row: Workspace) -> SysWorkspaceOut:
    """Project workspace ORM row to response schema."""

    return SysWorkspaceOut.model_validate(row)


def _create_payload(body: SysTenantCreateIn | SysWorkspaceCreateIn) -> dict[str, Any]:
    """Convert create body to service dict."""

    return body.model_dump()


def _patch_payload(body: SysTenantPatchIn | SysWorkspacePatchIn) -> dict[str, Any]:
    """Convert patch body to service dict excluding unset fields."""

    return body.model_dump(exclude_unset=True)


@router.get("", response_model=SysTenantListPageOut)
async def list_tenants(
    name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysTenantListPageOut:
    """Return paginated tenants for platform super administrators."""

    rows, total = await svc.list_tenants_page(
        session,
        page=page,
        page_size=page_size,
        name=name,
        status=status,
    )
    return SysTenantListPageOut(
        items=[_tenant_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SysTenantOut, status_code=201)
async def create_tenant(
    body: SysTenantCreateIn,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysTenantOut:
    """Create a tenant."""

    row = await svc.create_tenant(session, _create_payload(body))
    return _tenant_out(row)


@router.get("/{tenant_id}", response_model=SysTenantOut)
async def get_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysTenantOut:
    """Return one tenant."""

    row = await svc.get_tenant(session, tenant_id=tenant_id)
    return _tenant_out(row)


@router.patch("/{tenant_id}", response_model=SysTenantOut)
async def patch_tenant(
    tenant_id: uuid.UUID,
    body: SysTenantPatchIn,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysTenantOut:
    """Partially update a tenant."""

    row = await svc.patch_tenant(
        session,
        tenant_id=tenant_id,
        payload=_patch_payload(body),
    )
    return _tenant_out(row)


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> Response:
    """Cascade-delete a tenant and related rows."""

    await svc.delete_tenant(session, tenant_id=tenant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{tenant_id}/workspaces", response_model=SysWorkspaceListPageOut)
async def list_workspaces(
    tenant_id: uuid.UUID,
    name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysWorkspaceListPageOut:
    """Return paginated workspaces under a tenant."""

    rows, total = await svc.list_workspaces_page(
        session,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        name=name,
        status=status,
    )
    return SysWorkspaceListPageOut(
        items=[_workspace_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{tenant_id}/workspaces", response_model=SysWorkspaceOut, status_code=201)
async def create_workspace(
    tenant_id: uuid.UUID,
    body: SysWorkspaceCreateIn,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysWorkspaceOut:
    """Create a workspace under a tenant."""

    row = await svc.create_workspace(
        session,
        tenant_id=tenant_id,
        payload=_create_payload(body),
    )
    return _workspace_out(row)


@router.get("/{tenant_id}/workspaces/{workspace_id}", response_model=SysWorkspaceOut)
async def get_workspace(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysWorkspaceOut:
    """Return one workspace scoped to a tenant."""

    row = await svc.get_workspace(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    return _workspace_out(row)


@router.patch("/{tenant_id}/workspaces/{workspace_id}", response_model=SysWorkspaceOut)
async def patch_workspace(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: SysWorkspacePatchIn,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysWorkspaceOut:
    """Partially update a workspace."""

    row = await svc.patch_workspace(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        payload=_patch_payload(body),
    )
    return _workspace_out(row)


@router.delete("/{tenant_id}/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> Response:
    """Delete only the workspace row."""

    await svc.delete_workspace(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
