"""Delete per-engine OCR output rows when a task is re-queued (e.g. user retry)."""

from __future__ import annotations

from app.core.log import get_logger
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models_result import OcrFileMineru, OcrFilePaddleocr

log = get_logger(__name__)


async def delete_ocr_file_engine_result_rows(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    file_id: uuid.UUID,
    ocr_type: str,
) -> None:
    """Remove persisted result pages for ``file_id`` from the engine-specific table."""

    if ocr_type == "PADDLE_OCR":
        await session.execute(
            delete(OcrFilePaddleocr).where(
                OcrFilePaddleocr.workspace_id == workspace_id,
                OcrFilePaddleocr.file_id == file_id,
            )
        )
        log.info(
            "cleared ocr_file_paddleocr for retry file_id={} workspace_id={}",
            file_id,
            workspace_id,
        )
        return
    if ocr_type == "MINERU":
        await session.execute(
            delete(OcrFileMineru).where(
                OcrFileMineru.workspace_id == workspace_id,
                OcrFileMineru.file_id == file_id,
            )
        )
        log.info(
            "cleared ocr_file_mineru for retry file_id={} workspace_id={}",
            file_id,
            workspace_id,
        )
        return
    log.warning(
        "skip engine result cleanup on retry: unknown ocr_type={} file_id={}",
        ocr_type,
        file_id,
    )

