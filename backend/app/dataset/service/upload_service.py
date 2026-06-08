"""Upload files for dataset ingestion."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dataset.domain.constants import DATASET_ALLOWED_EXTENSIONS
from app.dataset.domain.db.models import DatasetUploadFile
from app.exceptions import AppError
from app.s3.service.s3_file_service import S3FileService


def _normalize_ext(file_name: str) -> str:
    """Return lowercase extension or raise."""

    ext = Path(file_name).suffix.lower().lstrip(".")
    if ext not in DATASET_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(DATASET_ALLOWED_EXTENSIONS))
        raise AppError("dataset.unsupported_file_type", f"不支持的文件类型，允许：{allowed}", 422)
    return ext


async def upload_dataset_file(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    file: UploadFile,
) -> DatasetUploadFile:
    """Persist one upload to S3 and register ``dataset_upload_file``."""

    if not file.filename:
        raise AppError("dataset.file_required", "请上传文件。", 422)
    ext = _normalize_ext(file.filename)
    payload = await file.read()
    limit = settings.dataset_single_file_size_limit_mb * 1024 * 1024
    if len(payload) > limit:
        raise AppError("dataset.file_too_large", "文件超过大小限制。", 422)

    s3 = S3FileService(session=session)
    upload = await s3.upload_file(
        workspace_id=workspace_id,
        module_prefix="dataset/uploads",
        file_name=file.filename,
        payload=payload,
        content_type=file.content_type,
    )
    row = DatasetUploadFile(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        storage_key=upload.object_key,
        name=file.filename,
        size=len(payload),
        extension=ext,
        mime_type=file.content_type,
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    return row
