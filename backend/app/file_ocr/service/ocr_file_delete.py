"""Application-level cleanup for ``ocr_file`` and dependent rows (no DB FK cascades)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models_log import OcrFileLog
from app.file_ocr.service.result_row_cleanup import delete_ocr_file_engine_result_rows

_ENGINE_TYPES = ("PADDLE_OCR", "MINERU")


async def delete_ocr_file_dependents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    """Remove engine result pages and execution logs for one OCR task."""

    for ocr_type in _ENGINE_TYPES:
        await delete_ocr_file_engine_result_rows(
            session,
            workspace_id=workspace_id,
            file_id=file_id,
            ocr_type=ocr_type,
        )
    await session.execute(
        delete(OcrFileLog).where(
            OcrFileLog.workspace_id == workspace_id,
            OcrFileLog.ocr_file_id == file_id,
        )
    )
