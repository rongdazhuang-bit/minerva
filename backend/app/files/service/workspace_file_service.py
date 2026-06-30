"""Unified workspace file operations over S3 or local active storage."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.files.domain.models import WorkspaceFileUploadResult
from app.local.infrastructure.local_gateway import LocalGateway
from app.local.service.local_file_service import LocalFileService
from app.s3.service.s3_file_service import S3FileService
from app.sys.file_storage.service.path_validation import resolve_effective_local_root
from app.sys.file_storage.service.storage_resolver import (
    ActiveStorage,
    resolve_active_storage,
)


class WorkspaceFileService:
    """Route object file IO to the workspace active storage backend."""

    def __init__(self, *, session: AsyncSession) -> None:
        """Bind one DB session used to resolve storage configuration."""

        self._session = session
        self._s3 = S3FileService(session=session)
        self._local = LocalFileService(session=session)

    async def upload_file(
        self,
        *,
        workspace_id: uuid.UUID,
        module_prefix: str,
        file_name: str,
        payload: bytes,
        content_type: str | None,
        presign_expires_in: int = 600,
    ) -> WorkspaceFileUploadResult:
        """Upload bytes and return metadata plus a download URL."""

        active = await resolve_active_storage(self._session, workspace_id=workspace_id)
        if active.kind == "S3":
            result = await self._s3.upload_file(
                workspace_id=workspace_id,
                module_prefix=module_prefix,
                file_name=file_name,
                payload=payload,
                content_type=content_type,
                presign_expires_in=presign_expires_in,
            )
        else:
            result = await self._local.upload_file(
                workspace_id=workspace_id,
                module_prefix=module_prefix,
                file_name=file_name,
                payload=payload,
                content_type=content_type,
                presign_expires_in=presign_expires_in,
            )
        return WorkspaceFileUploadResult(
            object_key=result.object_key,
            file_name=result.file_name,
            content_type=result.content_type,
            size=result.size,
            download_url=result.download_url,
        )

    async def read_object_bytes(
        self,
        *,
        workspace_id: uuid.UUID,
        object_key: str,
    ) -> bytes:
        """Load full object body from the active storage backend."""

        active = await resolve_active_storage(self._session, workspace_id=workspace_id)
        if active.kind == "S3":
            proxy = await self._s3.get_download_proxy(
                workspace_id=workspace_id,
                object_key=object_key,
            )
            try:
                return proxy.stream.read()
            finally:
                close = getattr(proxy.stream, "close", None)
                if callable(close):
                    close()
        _active, gateway = await self._resolve_local_gateway(
            workspace_id=workspace_id,
            active=active,
        )
        return gateway.get_object_bytes(object_key=object_key)

    async def create_download_url(
        self,
        *,
        workspace_id: uuid.UUID,
        object_key: str,
        presign_expires_in: int = 600,
    ) -> str:
        """Return a fresh download URL for one stored object."""

        active = await resolve_active_storage(self._session, workspace_id=workspace_id)
        if active.kind == "S3":
            redirect = await self._s3.get_download_redirect(
                workspace_id=workspace_id,
                object_key=object_key,
                presign_expires_in=presign_expires_in,
            )
            return redirect.url
        redirect = await self._local.get_download_redirect(
            workspace_id=workspace_id,
            object_key=object_key,
            presign_expires_in=presign_expires_in,
        )
        return redirect.url

    async def _resolve_local_gateway(
        self,
        *,
        workspace_id: uuid.UUID,
        active: ActiveStorage | None = None,
    ) -> tuple[ActiveStorage, LocalGateway]:
        """Build a local gateway for DEFAULT_LOCAL or LOCAL active storage."""

        resolved = active or await resolve_active_storage(
            self._session, workspace_id=workspace_id
        )
        if resolved.kind == "S3":
            raise AppError(
                "local.storage_not_active",
                "Local storage is not active for this workspace",
                422,
            )
        root = resolve_effective_local_root(
            workspace_id=workspace_id,
            local_path=resolved.local_path,
        )
        return resolved, LocalGateway(root=Path(root))
