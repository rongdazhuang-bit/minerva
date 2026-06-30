"""Validate and resolve agent vision image attachments."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.vision_mime import (
    allowed_vision_mime_set,
    assert_allowed_vision_extension,
    normalize_vision_mime,
)
from app.config import settings
from app.exceptions import AppError
from app.files.service.workspace_file_service import WorkspaceFileService

AGENT_VISION_MODULE_PREFIX = "agent_vision"


def assert_agent_vision_object_key(object_key: str) -> str:
    """Ensure attachment keys belong to the agent vision module prefix."""

    key = (object_key or "").strip()
    if not key.startswith(f"{AGENT_VISION_MODULE_PREFIX}/"):
        raise AppError("agent.vision_attachment_invalid", "Invalid attachment object_key", 422)
    return key


def validate_vision_upload_payload(
    *,
    payload: bytes,
    file_name: str,
    content_type: str | None,
) -> str:
    """Validate upload size, extension, and MIME; return normalized MIME."""

    if len(payload) > settings.agent_vision_image_max_bytes:
        raise AppError("agent.vision_file_too_large", "Image file is too large", 422)
    try:
        assert_allowed_vision_extension(file_name)
    except ValueError as exc:
        raise AppError("agent.vision_mime_not_allowed", "Image file type is not allowed", 422) from exc
    normalized = normalize_vision_mime(content_type)
    allowed = allowed_vision_mime_set(settings.agent_vision_image_allowed_mime)
    if normalized not in allowed:
        raise AppError("agent.vision_mime_not_allowed", "Image MIME type is not allowed", 422)
    return normalized or "application/octet-stream"


async def resolve_attachment_meta_for_run(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    items: list[dict],
) -> list[dict]:
    """Validate run attachments and enrich with download URLs for persistence."""

    if len(items) > settings.agent_vision_image_max_count:
        raise AppError("agent.vision_attachment_limit", "Too many image attachments", 422)

    file_service = WorkspaceFileService(session=session)
    resolved: list[dict] = []
    for item in items:
        object_key = assert_agent_vision_object_key(str(item.get("object_key") or ""))
        file_name = str(item.get("file_name") or Path(object_key).name)
        content_type = normalize_vision_mime(item.get("content_type"))
        try:
            raw = await file_service.read_object_bytes(
                workspace_id=workspace_id,
                object_key=object_key,
            )
        except AppError as exc:
            raise AppError(
                "agent.vision_attachment_invalid",
                "Attachment object not found",
                422,
            ) from exc
        if len(raw) > settings.agent_vision_image_max_bytes:
            raise AppError("agent.vision_file_too_large", "Image file is too large", 422)
        allowed = allowed_vision_mime_set(settings.agent_vision_image_allowed_mime)
        if content_type not in allowed:
            raise AppError("agent.vision_mime_not_allowed", "Image MIME type is not allowed", 422)
        download_url = await file_service.create_download_url(
            workspace_id=workspace_id,
            object_key=object_key,
        )
        resolved.append(
            {
                "object_key": object_key,
                "file_name": file_name,
                "content_type": content_type,
                "size": len(raw),
                "download_url": download_url,
            }
        )
    return resolved
