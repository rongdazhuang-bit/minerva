"""Business logic for workspace file storage settings CRUD."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.file_storage.domain.db.models import SysStorage
from app.sys.file_storage.infrastructure import repository as repo


_LEGACY_AUTH_TO_CANON: dict[str, str] = {
    "none": "NONE",
    "basic": "BASIC",
    "api_key": "API_KEY",
}


def _utc_now() -> datetime:
    """Return timezone-aware UTC timestamp for audit columns."""

    return datetime.now(UTC)


def _normalize_auth_type(value: str) -> str:
    """Normalize auth type token to canonical upper-case label."""

    raw = value.strip()
    if not raw:
        raise AppError("file_storage.auth_type_required", "auth_type is required", 422)
    return _LEGACY_AUTH_TO_CANON.get(raw.lower(), raw)


def _normalize_nullable_str(value: str | None) -> str | None:
    """Trim nullable strings and normalize blank to ``None``."""

    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _is_s3_storage(storage_type: str | None) -> bool:
    """Return True when storage type is S3 (case-insensitive)."""

    return (storage_type or "").strip().upper() == "S3"


def _assert_identity_fields(
    *,
    name: str | None,
    bucket_name: str | None,
    storage_type: str | None,
) -> None:
    """Require display ``name``; require ``bucket_name`` when type is S3."""

    if not (name or "").strip():
        raise AppError("file_storage.name_required", "name is required", 422)
    if _is_s3_storage(storage_type) and not (bucket_name or "").strip():
        raise AppError(
            "file_storage.bucket_name_required",
            "bucket_name is required for S3 storage",
            422,
        )


def _assert_auth_fields(
    *,
    auth_type: str,
    api_key: str | None,
    secret_key: str | None,
    auth_name: str | None,
    auth_passwd: str | None,
    strict: bool,
) -> None:
    """Validate credential bundle by auth type."""

    tag = _normalize_auth_type(auth_type)
    if tag == "API_KEY":
        if strict:
            if not (api_key or "").strip():
                raise AppError(
                    "file_storage.api_key_required",
                    "api_key is required for API_KEY auth",
                    422,
                )
            if not (secret_key or "").strip():
                raise AppError(
                    "file_storage.secret_key_required",
                    "secret_key is required for API_KEY auth",
                    422,
                )
            return
        if not (api_key or "").strip():
            raise AppError(
                "file_storage.api_key_required",
                "api_key is required for API_KEY auth",
                422,
            )
        return
    if tag == "BASIC":
        if strict and (not (auth_name or "").strip() or not (auth_passwd or "").strip()):
            raise AppError(
                "file_storage.basic_credentials_required",
                "auth_name and auth_passwd are required for BASIC auth",
                422,
            )
        return
    if tag == "NONE":
        return


async def list_storages_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[SysStorage], int]:
    """Return one paginated page and total count."""

    total = await repo.count_for_workspace(session, workspace_id=workspace_id)
    offset = (page - 1) * page_size
    rows = await repo.list_for_workspace_page(
        session,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
    )
    return list(rows), total


async def get_storage(
    session: AsyncSession, *, workspace_id: uuid.UUID, storage_id: uuid.UUID
) -> SysStorage:
    """Load one storage row or raise 404 when absent."""

    row = await repo.get_for_workspace(
        session, workspace_id=workspace_id, storage_id=storage_id
    )
    if row is None:
        raise AppError("file_storage.not_found", "File storage row not found", 404)
    return row


async def create_storage(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    data: dict[str, Any],
) -> SysStorage:
    """Create a workspace file storage row and persist it."""

    normalized_auth_type = _normalize_auth_type(str(data["auth_type"]))
    name = _normalize_nullable_str(data.get("name"))
    bucket_name = _normalize_nullable_str(data.get("bucket_name"))
    storage_type = _normalize_nullable_str(data.get("type"))
    endpoint_url = _normalize_nullable_str(data.get("endpoint_url"))
    api_key = _normalize_nullable_str(data.get("api_key"))
    secret_key = _normalize_nullable_str(data.get("secret_key"))
    auth_name = _normalize_nullable_str(data.get("auth_name"))
    auth_passwd = _normalize_nullable_str(data.get("auth_passwd"))

    _assert_identity_fields(
        name=name,
        bucket_name=bucket_name,
        storage_type=storage_type,
    )
    _assert_auth_fields(
        auth_type=normalized_auth_type,
        api_key=api_key,
        secret_key=secret_key,
        auth_name=auth_name,
        auth_passwd=auth_passwd,
        strict=True,
    )
    now = _utc_now()
    row = SysStorage(
        workspace_id=workspace_id,
        name=name,
        bucket_name=bucket_name,
        type=storage_type,
        enabled=bool(data.get("enabled", True)),
        auth_type=normalized_auth_type,
        endpoint_url=endpoint_url,
        api_key=api_key,
        secret_key=secret_key,
        auth_name=auth_name,
        auth_passwd=auth_passwd,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_storage(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    storage_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysStorage:
    """Update one storage row under workspace scope."""

    row = await get_storage(session, workspace_id=workspace_id, storage_id=storage_id)
    for key, value in patch.items():
        if key == "auth_type" and isinstance(value, str):
            setattr(row, key, _normalize_auth_type(value))
            continue
        if key in {
            "name",
            "bucket_name",
            "type",
            "endpoint_url",
            "api_key",
            "secret_key",
            "auth_name",
            "auth_passwd",
        }:
            setattr(row, key, _normalize_nullable_str(value))
            continue
        setattr(row, key, value)

    _assert_identity_fields(
        name=row.name,
        bucket_name=row.bucket_name,
        storage_type=row.type,
    )
    _assert_auth_fields(
        auth_type=row.auth_type,
        api_key=row.api_key,
        secret_key=row.secret_key,
        auth_name=row.auth_name,
        auth_passwd=row.auth_passwd,
        strict=False,
    )
    row.update_at = _utc_now()
    await session.commit()
    await session.refresh(row)
    return row


async def delete_storage(
    session: AsyncSession, *, workspace_id: uuid.UUID, storage_id: uuid.UUID
) -> None:
    """Delete one workspace storage row."""

    row = await get_storage(session, workspace_id=workspace_id, storage_id=storage_id)
    await session.delete(row)
    await session.commit()
