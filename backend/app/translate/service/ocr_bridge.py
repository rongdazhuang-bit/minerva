"""Create and poll ``ocr_file`` rows for scanned PDF translation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import AppError
from app.file_ocr.domain.db.models import OcrFile
from app.layout.load_ocr import load_layout_document_from_ocr_file
from app.layout.models import LayoutDocument
from app.translate.infrastructure import repository as translate_repo


async def run_ocr_and_load_layout(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    source_object_key: str,
    file_name: str,
    file_size: int | None,
) -> tuple[uuid.UUID, LayoutDocument | None]:
    """Insert INIT ``ocr_file``, wait until SUCCESS, return LDM when stored."""

    ocr_type = settings.doc_translate_default_ocr_type.strip()
    now = datetime.now(UTC)
    ocr_row = OcrFile(
        workspace_id=workspace_id,
        file_name=file_name,
        file_size=file_size,
        object_key=source_object_key,
        ocr_type=ocr_type,
        status="INIT",
        page_count=None,
        create_at=now,
        update_at=now,
    )
    session.add(ocr_row)
    await session.flush()
    await translate_repo.update_doc_translate_job(
        session,
        job_id=job_id,
        workspace_id=workspace_id,
        status="OCR_RUNNING",
        ocr_file_id=ocr_row.id,
    )
    await session.commit()

    deadline = asyncio.get_event_loop().time() + float(settings.doc_translate_ocr_timeout_seconds)
    interval = float(settings.doc_translate_ocr_poll_interval_seconds)
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(interval)
        row = (
            await session.execute(select(OcrFile).where(OcrFile.id == ocr_row.id))
        ).scalar_one_or_none()
        if row is None:
            raise AppError("translate.ocr_failed", "OCR 任务丢失。", 502)
        if row.status == "SUCCESS":
            layout_doc = await load_layout_document_from_ocr_file(
                session,
                workspace_id=workspace_id,
                ocr_file_id=ocr_row.id,
            )
            return ocr_row.id, layout_doc
        if row.status == "FAILED":
            raise AppError(
                "translate.ocr_failed",
                (row.remark or "OCR 处理失败。")[:500],
                502,
            )
    raise AppError("translate.ocr_failed", "OCR 等待超时。", 504)
