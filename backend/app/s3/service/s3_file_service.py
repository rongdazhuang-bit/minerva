"""Application service orchestrating workspace S3 file workflows."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.s3.domain.models import (
    S3DownloadProxy,
    S3DownloadRedirect,
    S3ListPage,
    S3StorageConfig,
    S3UploadResult,
)
from app.s3.infrastructure.s3_gateway import S3Gateway, create_s3_gateway
from app.sys.file_storage.domain.db.models import SysStorage

# Allowed characters for logical module prefixes in object keys.
_MODULE_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]*$")
# Allowed characters for full object keys.
_OBJECT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/._-]*$")


class S3FileService:
    """Workspace-scoped S3 file service with config loading from ``sys_storage``."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        gateway_factory: Callable[[S3StorageConfig], S3Gateway] | None = None,
    ) -> None:
        """Build the service with one DB session and S3 gateway factory."""

        self._session = session
        self._gateway_factory = gateway_factory or create_s3_gateway

    async def upload_file(
        self,
        *,
        workspace_id: uuid.UUID,
        module_prefix: str,
        file_name: str,
        payload: bytes,
        content_type: str | None,
        presign_expires_in: int = 600,
    ) -> S3UploadResult:
        """Upload one file and return key metadata with presigned download URL."""

        normalized_prefix = _normalize_module_prefix(module_prefix)
        config, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        object_key = _build_object_key(module_prefix=normalized_prefix, file_name=file_name)
        gateway.upload_object(
            bucket=config.bucket,
            object_key=object_key,
            payload=payload,
            content_type=content_type,
        )
        download_url = gateway.create_presigned_download_url(
            bucket=config.bucket,
            object_key=object_key,
            expires_in=presign_expires_in,
        )
        return S3UploadResult(
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
    ) -> S3ListPage:
        """List files with deterministic pagination under one workspace storage."""

        list_prefix = ""
        if module_prefix is not None:
            normalized_prefix = _normalize_module_prefix(module_prefix)
            list_prefix = f"{normalized_prefix}/"
        config, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        all_items = gateway.list_objects(bucket=config.bucket, prefix=list_prefix)
        total = len(all_items)
        start = (page - 1) * page_size
        end = start + page_size
        return S3ListPage(items=all_items[start:end], total=total, page=page, page_size=page_size)

    async def get_download_redirect(
        self,
        *,
        workspace_id: uuid.UUID,
        object_key: str,
        presign_expires_in: int = 600,
    ) -> S3DownloadRedirect:
        """Return redirect payload with presigned URL for one object."""

        normalized_key = _normalize_object_key(object_key)
        config, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        url = gateway.create_presigned_download_url(
            bucket=config.bucket,
            object_key=normalized_key,
            expires_in=presign_expires_in,
        )
        return S3DownloadRedirect(url=url)

    async def get_download_proxy(
        self,
        *,
        workspace_id: uuid.UUID,
        object_key: str,
    ) -> S3DownloadProxy:
        """Open and return proxy stream payload for one object."""

        normalized_key = _normalize_object_key(object_key)
        config, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        return gateway.open_download_stream(bucket=config.bucket, object_key=normalized_key)

    async def delete_file(self, *, workspace_id: uuid.UUID, object_key: str) -> None:
        """Delete one object by key from workspace S3 storage."""

        normalized_key = _normalize_object_key(object_key)
        config, gateway = await self._resolve_gateway(workspace_id=workspace_id)
        gateway.delete_object(bucket=config.bucket, object_key=normalized_key)

    async def _resolve_gateway(self, *, workspace_id: uuid.UUID) -> tuple[S3StorageConfig, S3Gateway]:
        """Load storage config and build one gateway instance."""

        config = await self._load_storage_config(workspace_id=workspace_id)
        return config, self._gateway_factory(config)

    async def _load_storage_config(self, *, workspace_id: uuid.UUID) -> S3StorageConfig:
        """Load and validate S3 storage config from ``sys_storage``."""

        result = await self._session.execute(
            sa.select(SysStorage)
            .where(SysStorage.workspace_id == workspace_id)
            .order_by(
                SysStorage.update_at.desc().nulls_last(),
                SysStorage.create_at.desc().nulls_last(),
                SysStorage.id.desc(),
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError("s3.storage_not_found", "S3 storage not found", 404)
        if not row.enabled:
            raise AppError("s3.storage_not_enabled", "S3 storage is disabled", 422)

        storage_type = (row.type or "").strip().upper()
        if storage_type != "S3":
            raise AppError("s3.storage_type_invalid", "Storage type must be S3", 422)

        auth_type = (row.auth_type or "").strip().upper()
        if auth_type not in {"API_KEY", "BASIC"}:
            raise AppError("s3.auth_invalid", "S3 auth type must be API_KEY or BASIC", 422)
        if auth_type == "API_KEY" and not (row.api_key or "").strip():
            raise AppError("s3.auth_invalid", "API_KEY auth requires api_key", 422)
        if auth_type == "BASIC" and (
            not (row.auth_name or "").strip() or not (row.auth_passwd or "").strip()
        ):
            raise AppError("s3.auth_invalid", "BASIC auth requires auth_name/auth_passwd", 422)

        bucket = (row.name or "").strip()
        if not bucket:
            raise AppError("s3.request_failed", "S3 bucket is required in sys_storage.name", 502)
        endpoint_url = (row.endpoint_url or "").strip() or None
        return S3StorageConfig(
            bucket=bucket,
            endpoint_url=endpoint_url,
            auth_type=auth_type,
            api_key=(row.api_key or "").strip() or None,
            auth_name=(row.auth_name or "").strip() or None,
            auth_passwd=(row.auth_passwd or "").strip() or None,
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
        raise AppError("s3.module_prefix_invalid", "Invalid module_prefix", 422)
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
        raise AppError("s3.object_key_invalid", "Invalid object_key", 422)
    return key


def _build_object_key(*, module_prefix: str, file_name: str) -> str:
    """Build object key: ``module_prefix/YYYY/MM/<uuid>.<ext>``."""

    now = datetime.now(UTC)
    suffix = Path(file_name).suffix.strip()
    ext = suffix if suffix.startswith(".") else ""
    return f"{module_prefix}/{now.year:04d}/{now.month:02d}/{uuid.uuid4()}{ext}"
