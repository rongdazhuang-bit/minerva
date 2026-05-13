"""Load raw object bytes from workspace S3 for OCR workers."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.s3.service.s3_file_service import S3FileService


async def read_workspace_object_bytes(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    object_key: str,
) -> bytes:
    """Stream the entire object body into memory for Base64 encoding to OCR vendors."""

    service = S3FileService(session=session)
    proxy = await service.get_download_proxy(workspace_id=workspace_id, object_key=object_key)
    try:
        return proxy.stream.read()
    finally:
        close = getattr(proxy.stream, "close", None)
        if callable(close):
            close()
