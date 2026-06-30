"""Application service orchestrating workspace local file workflows."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.local.domain.models import (
    LocalDownloadProxy,
    LocalDownloadRedirect,
    LocalListPage,
    LocalUploadResult,
)
from app.local.infrastructure.download_token import create_download_token
from app.local.infrastructure.local_gateway import LocalGateway
from app.sys.file_storage.service.path_validation import resolve_object_file
from app.sys.file_storage.service.storage_resolver import (
    ActiveStorage,
    resolve_active_storage,
)

# Allowed characters for logical module prefixes in object keys.
_MODULE_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]*$")
# Allowed characters for full object keys.
_OBJECT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/._-]*$")


class LocalFileService:
    """Workspace-scoped local file service with active storage resolution."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        gateway_factory: Callable[[Path], LocalGateway] | None = None,
    ) -> None:
        """Build the service with one DB session and local gateway factory."""

        self._session = session
        self._gateway_factory = gateway_factory or (lambda root: LocalGateway(root=root))

    async def upload_file(
        self,
        *,
        workspace_id: uuid.UUID,
        module_prefix: str,
        file_name: str,
        payload: bytes,
        content_type: str | None,
        presign_expires_in: int = 600,
    ) -> LocalUploadResult:
        """Upload one file and return key metadata with signed download URL."""

        normalized_prefix = _normalize_module_prefix(module_prefix)
        active, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        object_key = _build_object_key(module_prefix=normalized_prefix, file_name=file_name)
        resolve_object_file(
            workspace_id=workspace_id,
            local_path=active.local_path,
            object_key=object_key,
        )
        gateway.put_object(
            object_key=object_key,
            payload=payload,
            content_type=content_type,
        )
        download_url = _build_local_download_url(
            workspace_id=workspace_id,
            object_key=object_key,
            expires_in=presign_expires_in,
        )
        return LocalUploadResult(
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size=len(payload),
            download_url=download_url,
        )

    async def list_files(
        self,
        *,
        workspace_id: uuid.UUID,
        module_prefix: str | None,
        page: int,
        page_size: int,
    ) -> LocalListPage:
        """List files with deterministic pagination under one workspace storage."""

        list_prefix = ""
        if module_prefix is not None:
            normalized_prefix = _normalize_module_prefix(module_prefix)
            list_prefix = f"{normalized_prefix}/"
        _, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        all_items = gateway.list_objects(prefix=list_prefix)
        total = len(all_items)
        start = (page - 1) * page_size
        end = start + page_size
        return LocalListPage(items=all_items[start:end], total=total, page=page, page_size=page_size)

    async def get_download_redirect(
        self,
        *,
        workspace_id: uuid.UUID,
        object_key: str,
        presign_expires_in: int = 600,
    ) -> LocalDownloadRedirect:
        """Return redirect payload with signed download URL for one object."""

        normalized_key = _normalize_object_key(object_key)
        active, _ = await self._resolve_gateway(workspace_id=workspace_id)
        resolve_object_file(
            workspace_id=workspace_id,
            local_path=active.local_path,
            object_key=normalized_key,
        )
        url = _build_local_download_url(
            workspace_id=workspace_id,
            object_key=normalized_key,
            expires_in=presign_expires_in,
        )
        return LocalDownloadRedirect(url=url)

    async def get_download_proxy(
        self,
        *,
        workspace_id: uuid.UUID,
        object_key: str,
    ) -> LocalDownloadProxy:
        """Open and return proxy stream payload for one object."""

        normalized_key = _normalize_object_key(object_key)
        active, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        resolve_object_file(
            workspace_id=workspace_id,
            local_path=active.local_path,
            object_key=normalized_key,
        )
        return gateway.open_download_stream(object_key=normalized_key)

    async def delete_file(self, *, workspace_id: uuid.UUID, object_key: str) -> None:
        """Delete one object by key from workspace local storage."""

        normalized_key = _normalize_object_key(object_key)
        active, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        resolve_object_file(
            workspace_id=workspace_id,
            local_path=active.local_path,
            object_key=normalized_key,
        )
        gateway.delete_object(object_key=normalized_key)

    async def _resolve_gateway(
        self, *, workspace_id: uuid.UUID
    ) -> tuple[ActiveStorage, LocalGateway]:
        """Resolve active storage root and build one gateway instance."""

        active = await resolve_active_storage(self._session, workspace_id=workspace_id)
        if active.kind == "S3":
            raise AppError(
                "local.storage_not_active",
                "Local storage is not active for this workspace",
                422,
            )
        root = _resolve_effective_root(workspace_id=workspace_id, active=active)
        return active, self._gateway_factory(root)


def _resolve_effective_root(*, workspace_id: uuid.UUID, active: ActiveStorage) -> Path:
    """Return filesystem root for LOCAL or DEFAULT_LOCAL active storage."""

    from app.sys.file_storage.service.path_validation import resolve_effective_local_root

    return resolve_effective_local_root(
        workspace_id=workspace_id,
        local_path=active.local_path,
    )


def _build_local_download_url(
    *,
    workspace_id: uuid.UUID,
    object_key: str,
    expires_in: int,
) -> str:
    """Build application download URL with signed token query parameters."""

    token = create_download_token(
        workspace_id=workspace_id,
        object_key=object_key,
        expires_in=expires_in,
    )
    encoded_key = quote(object_key, safe="")
    return (
        f"/workspaces/{workspace_id}/local/files:download"
        f"?object_key={encoded_key}&token={token}"
    )


def _normalize_module_prefix(module_prefix: str) -> str:
    """Validate and normalize module prefix used to generate object keys."""

    prefix = module_prefix.strip()
    if (
        not prefix
        or prefix.startswith("/")
        or prefix.endswith("/")
        or "//" in prefix
        or ".." in prefix
        or not _MODULE_PREFIX_PATTERN.fullmatch(prefix)
    ):
        raise AppError("local.module_prefix_invalid", "Invalid module_prefix", 422)
    return prefix


def _normalize_object_key(object_key: str) -> str:
    """Validate and normalize object key provided by API callers."""

    key = object_key.strip()
    if (
        not key
        or key.startswith("/")
        or key.endswith("/")
        or "//" in key
        or ".." in key
        or not _OBJECT_KEY_PATTERN.fullmatch(key)
    ):
        raise AppError("local.object_key_invalid", "Invalid object_key", 422)
    return key


def _build_object_key(*, module_prefix: str, file_name: str) -> str:
    """Build object key: ``module_prefix/YYYY/MM/<uuid>.<ext>``."""

    now = datetime.now(UTC)
    suffix = Path(file_name).suffix.strip()
    ext = suffix if suffix.startswith(".") else ""
    return f"{module_prefix}/{now.year:04d}/{now.month:02d}/{uuid.uuid4()}{ext}"
