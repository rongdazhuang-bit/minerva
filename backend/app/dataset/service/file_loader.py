"""Download uploaded dataset source files from workspace S3."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.db.models import DatasetUploadFile
from app.exceptions import AppError
from app.s3.service.s3_file_service import S3FileService


async def load_upload_bytes(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    upload_id: uuid.UUID,
) -> tuple[DatasetUploadFile, bytes]:
    """Fetch upload row and read object bytes."""

    row = await session.get(DatasetUploadFile, upload_id)
    if row is None or row.workspace_id != workspace_id:
        raise AppError("dataset.upload_not_found", "上传文件不存在。", 404)
    s3 = S3FileService(session=session)
    stream = await s3.open_download_stream(
        workspace_id=workspace_id,
        object_key=row.storage_key,
    )
    payload = stream.body.read()
    return row, payload
