"""Validate, resolve, persist, and expose agent message attachments."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import AgentMessageAttachment
from app.agent.infrastructure.attachment_kind import (
    allowed_attachment_mime_set,
    attachment_kind_from_mime,
)
from app.agent.infrastructure.vision_mime import (
    allowed_vision_mime_set,
    assert_allowed_vision_extension,
    normalize_vision_mime,
)
from app.config import settings
from app.exceptions import AppError
from app.files.service.workspace_file_service import WorkspaceFileService
from app.local.service.local_file_service import LocalFileService
from app.s3.service.s3_file_service import S3FileService
from app.sys.file_storage.service.storage_resolver import resolve_active_storage

# Module prefix for new agent attachment uploads.
AGENT_ATTACHMENT_MODULE_PREFIX = "agent_attachment"
# Legacy vision-only uploads remain readable for backward compatibility.
LEGACY_AGENT_VISION_PREFIX = "agent_vision"
# Alias kept for callers that still import the old constant name.
AGENT_VISION_MODULE_PREFIX = LEGACY_AGENT_VISION_PREFIX


def assert_agent_attachment_object_key(object_key: str) -> str:
    """Ensure attachment keys belong to agent_attachment or legacy agent_vision prefix."""

    key = (object_key or "").strip()
    if key.startswith(f"{AGENT_ATTACHMENT_MODULE_PREFIX}/"):
        return key
    if key.startswith(f"{LEGACY_AGENT_VISION_PREFIX}/"):
        return key
    raise AppError("agent.attachment_invalid", "Invalid attachment object_key", 422)


def assert_agent_vision_object_key(object_key: str) -> str:
    """Backward-compatible alias for ``assert_agent_attachment_object_key``."""

    return assert_agent_attachment_object_key(object_key)


def validate_attachment_upload_payload(
    *,
    payload: bytes,
    file_name: str,
    content_type: str | None,
) -> str:
    """Validate upload size, MIME whitelist, and image extension; return normalized MIME."""

    if len(payload) > settings.agent_attachment_max_bytes:
        raise AppError("agent.attachment_file_too_large", "Attachment file is too large", 422)

    normalized = normalize_vision_mime(content_type)
    mime_for_kind = normalized or (content_type or "").strip().lower()
    is_image = mime_for_kind.startswith("image/")

    if not is_image:
        raise AppError(
            "agent.attachment_mime_not_allowed",
            "Only image attachments are allowed",
            422,
        )

    try:
        assert_allowed_vision_extension(file_name)
    except ValueError as exc:
        raise AppError(
            "agent.attachment_mime_not_allowed",
            "Attachment file type is not allowed",
            422,
        ) from exc
    normalized = normalize_vision_mime(content_type)

    check_mime = normalized or (content_type or "").strip().lower() or "application/octet-stream"
    allowed = allowed_attachment_mime_set(settings.agent_attachment_allowed_mime)
    if check_mime not in allowed:
        raise AppError(
            "agent.attachment_mime_not_allowed",
            "Attachment MIME type is not allowed",
            422,
        )
    return normalized or check_mime


def validate_vision_upload_payload(
    *,
    payload: bytes,
    file_name: str,
    content_type: str | None,
) -> str:
    """Thin wrapper around ``validate_attachment_upload_payload`` for legacy upload routes."""

    return validate_attachment_upload_payload(
        payload=payload,
        file_name=file_name,
        content_type=content_type,
    )


async def resolve_attachment_meta_for_run(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    items: list[dict],
) -> list[dict]:
    """Validate run attachments and return metadata without download URLs."""

    if len(items) > settings.agent_attachment_max_count:
        raise AppError("agent.attachment_limit", "Too many attachments", 422)

    file_service = WorkspaceFileService(session=session)
    vision_allowed = allowed_vision_mime_set(settings.agent_vision_image_allowed_mime)
    resolved: list[dict] = []
    image_count = 0

    for item in items:
        object_key = assert_agent_attachment_object_key(str(item.get("object_key") or ""))
        file_name = str(item.get("file_name") or Path(object_key).name)
        raw_content_type = item.get("content_type")
        content_type = normalize_vision_mime(raw_content_type) or (
            str(raw_content_type or "").strip().lower() or None
        )
        kind = attachment_kind_from_mime(content_type)
        if kind != "image":
            raise AppError(
                "agent.attachment_mime_not_allowed",
                "Only image attachments are allowed",
                422,
            )

        try:
            raw = await file_service.read_object_bytes(
                workspace_id=workspace_id,
                object_key=object_key,
            )
        except AppError as exc:
            raise AppError(
                "agent.attachment_invalid",
                "Attachment object not found",
                422,
            ) from exc

        size = len(raw)
        if size > settings.agent_attachment_max_bytes:
            raise AppError("agent.attachment_file_too_large", "Attachment file is too large", 422)

        allowed = allowed_attachment_mime_set(settings.agent_attachment_allowed_mime)
        if content_type not in allowed:
            raise AppError(
                "agent.attachment_mime_not_allowed",
                "Attachment MIME type is not allowed",
                422,
            )

        image_count += 1
        if image_count > settings.agent_vision_image_max_count:
            raise AppError(
                "agent.vision_attachment_limit",
                "Too many image attachments",
                422,
            )
        if size > settings.agent_vision_image_max_bytes:
            raise AppError("agent.vision_file_too_large", "Image file is too large", 422)
        if content_type not in vision_allowed:
            raise AppError(
                "agent.vision_mime_not_allowed",
                "Image MIME type is not allowed",
                422,
            )

        resolved.append(
            {
                "object_key": object_key,
                "file_name": file_name,
                "content_type": content_type,
                "size": size,
                "kind": kind,
            }
        )
    return resolved


async def build_attachment_rows_for_message(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    created_by: uuid.UUID | None,
    items: list[dict],
) -> list[AgentMessageAttachment]:
    """Create ORM attachment rows from run-validated items with storage_kind snapshot."""

    active = await resolve_active_storage(session, workspace_id=workspace_id)
    storage_kind = active.kind
    rows: list[AgentMessageAttachment] = []
    for item in items:
        content_type = item.get("content_type")
        rows.append(
            AgentMessageAttachment(
                workspace_id=workspace_id,
                session_id=session_id,
                message_id=message_id,
                object_key=item["object_key"],
                storage_kind=storage_kind,
                file_name=item.get("file_name"),
                content_type=content_type,
                size=item.get("size"),
                kind=item.get("kind") or attachment_kind_from_mime(content_type),
                created_by=created_by,
            )
        )
    return rows


async def attachment_rows_to_api_out(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rows: list[AgentMessageAttachment],
) -> list[dict]:
    """Mint fresh download URLs for persisted attachment rows (not stored in DB)."""

    file_service = WorkspaceFileService(session=session)
    expires = settings.agent_attachment_download_expires_in
    out: list[dict] = []
    for row in rows:
        url = await file_service.create_download_url(
            workspace_id=workspace_id,
            object_key=row.object_key,
            presign_expires_in=expires,
        )
        out.append(
            {
                "id": row.id,
                "object_key": row.object_key,
                "file_name": row.file_name,
                "content_type": row.content_type,
                "size": row.size,
                "kind": row.kind,
                "download_url": url,
            }
        )
    return out


async def legacy_meta_attachments_to_api_out(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    meta_attachments: list[dict],
) -> list[dict]:
    """Refresh download URLs for legacy JSONB attachment metadata."""

    file_service = WorkspaceFileService(session=session)
    expires = settings.agent_attachment_download_expires_in
    out: list[dict] = []
    for item in meta_attachments:
        if not isinstance(item, dict):
            continue
        object_key = str(item.get("object_key") or "").strip()
        if not object_key:
            continue
        url = await file_service.create_download_url(
            workspace_id=workspace_id,
            object_key=object_key,
            presign_expires_in=expires,
        )
        content_type = item.get("content_type")
        out.append(
            {
                "object_key": object_key,
                "file_name": item.get("file_name"),
                "content_type": content_type,
                "size": item.get("size"),
                "kind": attachment_kind_from_mime(
                    str(content_type) if content_type is not None else None
                ),
                "download_url": url,
            }
        )
    return out


def collect_legacy_meta_attachment_object_keys(
    messages: Iterable[Any],
    *,
    exclude_keys: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Collect attachment object keys from message meta_json not already in the DB table."""

    excluded = exclude_keys or frozenset()
    seen: set[str] = set()
    keys: list[str] = []
    for message in messages:
        meta_json = getattr(message, "meta_json", None)
        if not isinstance(meta_json, dict):
            continue
        raw = meta_json.get("attachments")
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            object_key = str(item.get("object_key") or "").strip()
            if not object_key or object_key in excluded or object_key in seen:
                continue
            try:
                assert_agent_attachment_object_key(object_key)
            except AppError:
                continue
            seen.add(object_key)
            keys.append(object_key)
    return keys


async def delete_legacy_meta_attachment_objects(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    object_keys: list[str],
) -> None:
    """Delete storage objects referenced only by legacy meta_json attachment metadata."""

    if not object_keys:
        return
    active = await resolve_active_storage(session, workspace_id=workspace_id)
    s3_service = S3FileService(session=session)
    local_service = LocalFileService(session=session)
    for object_key in object_keys:
        if active.kind == "S3":
            await s3_service.delete_file(workspace_id=workspace_id, object_key=object_key)
        else:
            await local_service.delete_file(workspace_id=workspace_id, object_key=object_key)


async def delete_storage_objects_for_rows(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rows: list[AgentMessageAttachment],
) -> None:
    """Delete stored objects for attachment rows using each row's storage_kind snapshot."""

    s3_service = S3FileService(session=session)
    local_service = LocalFileService(session=session)
    for row in rows:
        if row.storage_kind == "S3":
            await s3_service.delete_file(workspace_id=workspace_id, object_key=row.object_key)
        elif row.storage_kind in {"LOCAL", "DEFAULT_LOCAL"}:
            await local_service.delete_file(workspace_id=workspace_id, object_key=row.object_key)
        else:
            raise AppError(
                "agent.attachment_invalid",
                f"Unsupported attachment storage_kind: {row.storage_kind}",
                422,
            )
