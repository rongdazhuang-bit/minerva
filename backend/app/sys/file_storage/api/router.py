"""Workspace-scoped CRUD routes for file storage settings."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    require_workspace_member,
    require_workspace_owner_or_admin,
)
from app.dependencies import get_db
from app.domain.identity.models import User
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.file_storage.api.schemas import (
    FileStorageCreateIn,
    FileStorageDetailOut,
    FileStorageListItemOut,
    FileStorageListPageOut,
    FileStoragePatchIn,
)
from app.sys.file_storage.domain.db.models import SysStorage
from app.sys.file_storage.service import file_storage_service as svc

router = APIRouter(
    prefix="/workspaces/{workspace_id}/file-storages",
    tags=["file-storages"],
)


def _to_list_item(row: SysStorage) -> FileStorageListItemOut:
    """Project ORM row to list response model."""

    return FileStorageListItemOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        type=row.type,
        enabled=row.enabled,
        auth_type=row.auth_type,
        endpoint_url=row.endpoint_url,
        auth_name=row.auth_name,
        has_api_key=bool(row.api_key),
        has_password=bool(row.auth_passwd),
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_detail(row: SysStorage) -> FileStorageDetailOut:
    """Project ORM row to detail response model."""

    return FileStorageDetailOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        type=row.type,
        enabled=row.enabled,
        auth_type=row.auth_type,
        endpoint_url=row.endpoint_url,
        api_key=row.api_key,
        auth_name=row.auth_name,
        auth_passwd=row.auth_passwd,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_create_data(body: FileStorageCreateIn) -> dict[str, Any]:
    """Convert create schema to service payload."""

    return {
        "name": body.name,
        "type": body.type,
        "enabled": body.enabled,
        "auth_type": body.auth_type,
        "endpoint_url": body.endpoint_url,
        "api_key": body.api_key,
        "auth_name": body.auth_name,
        "auth_passwd": body.auth_passwd,
    }


def _to_patch_data(body: FileStoragePatchIn) -> dict[str, Any]:
    """Convert patch schema to service payload."""

    data = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            patch[key] = value.strip()
            continue
        patch[key] = value
    return patch


@router.get("", response_model=FileStorageListPageOut)
async def list_file_storages(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> FileStorageListPageOut:
    """Return paginated file storage list in current workspace."""

    rows, total = await svc.list_storages_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
    )
    return FileStorageListPageOut(items=[_to_list_item(r) for r in rows], total=total)


@router.post("", response_model=FileStorageDetailOut, status_code=status.HTTP_201_CREATED)
async def create_file_storage(
    workspace_id: uuid.UUID,
    body: FileStorageCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> FileStorageDetailOut:
    """Create one file storage row in current workspace."""

    row = await svc.create_storage(
        session,
        workspace_id=workspace_id,
        data=_to_create_data(body),
    )
    return _to_detail(row)


@router.get("/{storage_id}", response_model=FileStorageDetailOut)
async def get_file_storage(
    workspace_id: uuid.UUID,
    storage_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> FileStorageDetailOut:
    """Load full detail for one file storage row."""

    row = await svc.get_storage(
        session,
        workspace_id=workspace_id,
        storage_id=storage_id,
    )
    return _to_detail(row)


@router.patch("/{storage_id}", response_model=FileStorageDetailOut)
async def patch_file_storage(
    workspace_id: uuid.UUID,
    storage_id: uuid.UUID,
    body: FileStoragePatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> FileStorageDetailOut:
    """Patch one file storage row and return full detail."""

    patch = _to_patch_data(body)
    if not patch:
        row = await svc.get_storage(
            session,
            workspace_id=workspace_id,
            storage_id=storage_id,
        )
        return _to_detail(row)
    row = await svc.update_storage(
        session,
        workspace_id=workspace_id,
        storage_id=storage_id,
        patch=patch,
    )
    return _to_detail(row)


@router.delete("/{storage_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_file_storage(
    workspace_id: uuid.UUID,
    storage_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Delete one file storage row."""

    await svc.delete_storage(
        session,
        workspace_id=workspace_id,
        storage_id=storage_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
