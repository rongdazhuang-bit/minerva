"""Create and query document translation jobs."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import enqueue_task
from app.config import settings
from app.exceptions import AppError
from app.s3.service.s3_file_service import S3FileService
from app.translate.domain.constants import (
    DOC_TRANSLATE_ALLOWED_EXTS,
    DOC_TRANSLATE_LIST_DEFAULT_LIMIT,
    DOC_TRANSLATE_RUN_TASK_NAME,
    DOC_TRANSLATE_SEGMENTS_MAX_RETURN,
    DOC_TRANSLATE_STATUS_PENDING,
)
from app.translate.infrastructure import repository as translate_repo
from app.translate.service.translate_dict_seed import ensure_translate_status_dicts
from app.translate.service.translate_llm import _assert_translate_model


def _normalize_ext(file_name: str) -> str:
    ext = Path(file_name).suffix.lower().lstrip(".")
    if ext not in DOC_TRANSLATE_ALLOWED_EXTS:
        raise AppError(
            "translate.unsupported_ext",
            f"不支持的文件格式，允许：{', '.join(sorted(DOC_TRANSLATE_ALLOWED_EXTS))}",
            422,
        )
    return ext


async def create_job_from_upload(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID | None,
    file: UploadFile,
    source_lang: str,
    target_lang: str,
    model_id: uuid.UUID,
) -> uuid.UUID:
    """Upload source file, persist job, enqueue Celery worker."""

    if not file.filename:
        raise AppError("translate.file_required", "请上传文件。", 422)
    ext = _normalize_ext(file.filename)
    payload = await file.read()
    if len(payload) > settings.doc_translate_max_file_bytes:
        raise AppError("translate.file_too_large", "文件超过大小限制。", 422)
    if not source_lang.strip() or not target_lang.strip():
        raise AppError("translate.lang_required", "请选择源语言与目标语言。", 422)

    await _assert_translate_model(session, workspace_id=workspace_id, model_id=model_id)
    await ensure_translate_status_dicts(session, workspace_id=workspace_id)

    s3 = S3FileService(session=session)
    upload = await s3.upload_file(
        workspace_id=workspace_id,
        module_prefix="translate/source",
        file_name=file.filename,
        payload=payload,
        content_type=file.content_type,
    )
    row = await translate_repo.create_doc_translate_job(
        session,
        workspace_id=workspace_id,
        created_by=created_by,
        title=file.filename,
        file_name=file.filename,
        file_ext=ext,
        source_lang=source_lang.strip(),
        target_lang=target_lang.strip(),
        model_id=model_id,
        status=DOC_TRANSLATE_STATUS_PENDING,
        source_object_key=upload.object_key,
    )
    await session.commit()
    enqueue_task(DOC_TRANSLATE_RUN_TASK_NAME, args=[str(row.id)])
    return row.id
