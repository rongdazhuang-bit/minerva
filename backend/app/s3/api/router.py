"""Workspace-scoped S3 file operation routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.core.domain.identity.models import User
from app.exceptions import AppError
from app.pagination import DEFAULT_PAGE_SIZE
from app.s3.api.schemas import S3DownloadMode, S3FileListItemOut, S3FileListOut, S3FileUploadOut
from app.s3.service.s3_file_service import S3FileService

router = APIRouter(prefix="/workspaces/{workspace_id}/s3/files", tags=["s3-files"])


def get_s3_file_service(session: AsyncSession = Depends(get_db)) -> S3FileService:
    """Build one request-scoped S3 file service."""

    return S3FileService(session=session)


@router.post(":upload", response_model=S3FileUploadOut, status_code=status.HTTP_201_CREATED)
async def upload_workspace_s3_file(
    workspace_id: uuid.UUID,
    module_prefix: str = Query(min_length=1),
    file: UploadFile | None = File(default=None),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    service: S3FileService = Depends(get_s3_file_service),
) -> S3FileUploadOut:
    """Upload one file to workspace S3 storage."""

    if file is None:
        raise AppError("s3.file_required", "file is required", 422)
    payload = await file.read()
    result = await service.upload_file(
        workspace_id=workspace_id,
        module_prefix=module_prefix,
        file_name=file.filename or "upload.bin",
        payload=payload,
        content_type=file.content_type,
    )
    return S3FileUploadOut(
        object_key=result.object_key,
        file_name=result.file_name,
        content_type=result.content_type,
        size=result.size,
        download_url=result.download_url,
    )


@router.get("", response_model=S3FileListOut)
async def list_workspace_s3_files(
    workspace_id: uuid.UUID,
    module_prefix: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    service: S3FileService = Depends(get_s3_file_service),
) -> S3FileListOut:
    """List workspace S3 files under one optional module prefix."""

    result = await service.list_files(
        workspace_id=workspace_id,
        module_prefix=module_prefix,
        page=page,
        page_size=page_size,
    )
    return S3FileListOut(
        items=[
            S3FileListItemOut(
                object_key=item.object_key,
                size=item.size,
                last_modified=item.last_modified,
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(":download", response_model=None)
async def download_workspace_s3_file(
    workspace_id: uuid.UUID,
    object_key: str = Query(min_length=1),
    mode: S3DownloadMode = Query(default=S3DownloadMode.redirect),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    service: S3FileService = Depends(get_s3_file_service),
) -> Response:
    """Download one S3 file by redirect URL or proxy stream."""

    if mode == S3DownloadMode.redirect:
        redirect = await service.get_download_redirect(
            workspace_id=workspace_id,
            object_key=object_key,
        )
        return RedirectResponse(url=redirect.url, status_code=status.HTTP_302_FOUND)

    proxied = await service.get_download_proxy(workspace_id=workspace_id, object_key=object_key)
    file_name = PurePosixPath(object_key).name or "download.bin"
    headers: dict[str, str] = {"Content-Disposition": f'attachment; filename="{file_name}"'}
    if proxied.content_length is not None:
        headers["Content-Length"] = str(proxied.content_length)
    return StreamingResponse(
        content=_iter_proxy_stream(proxied.stream),
        media_type=proxied.content_type or "application/octet-stream",
        headers=headers,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_workspace_s3_file(
    workspace_id: uuid.UUID,
    object_key: str = Query(min_length=1),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    service: S3FileService = Depends(get_s3_file_service),
) -> Response:
    """Delete one S3 object key from workspace storage."""

    await service.delete_file(workspace_id=workspace_id, object_key=object_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _iter_proxy_stream(stream) -> Iterator[bytes]:
    """Yield proxied stream chunks and close body at end."""

    try:
        while True:
            chunk = stream.read(1024 * 64)
            if not chunk:
                break
            yield chunk
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
