"""Assemble markdown-pages API payload for SUCCESS ``ocr_file`` rows."""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.file_ocr.api.schemas import OcrFileMarkdownPageOut, OcrFileMarkdownPagesOut
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.service.result_read.registry import get_file_ocr_result_read_strategy

_LOGGER = logging.getLogger(__name__)


def _parse_markdown_images(raw: str | None) -> dict[str, str] | None:
    """Parse ``markdown_images`` JSON text into a ``str -> str`` map, or ``None`` if invalid."""

    if raw is None or str(raw).strip() == "":
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.warning("markdown_images JSON decode failed for OCR result page")
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, str):
            _LOGGER.warning("markdown_images contains non-string key or value")
            return None
        out[k] = v
    return out if out else None


async def get_ocr_file_markdown_pages(
    *,
    session: AsyncSession,
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
) -> OcrFileMarkdownPagesOut:
    """Load ordered markdown pages for a SUCCESS ``ocr_file`` in the workspace."""

    result = await session.execute(
        select(OcrFile).where(OcrFile.id == ocr_file_id, OcrFile.workspace_id == workspace_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("ocr_file.not_found", "OCR task not found", 404)
    if row.status != "SUCCESS":
        raise AppError(
            "ocr_file.detail_requires_success",
            "Task must be SUCCESS to load markdown pages",
            409,
        )
    try:
        read_strategy = get_file_ocr_result_read_strategy(row.ocr_type)
    except KeyError:
        raise AppError(
            "ocr_file.unsupported_detail_type",
            "OCR type does not support markdown detail",
            422,
        ) from None
    raw_pages = await read_strategy.load_pages(
        session=session, workspace_id=workspace_id, file_id=ocr_file_id
    )
    pages = [
        OcrFileMarkdownPageOut(
            page_index=p.page_index,
            markdown_text=p.markdown_text,
            images=_parse_markdown_images(p.markdown_images),
        )
        for p in raw_pages
    ]
    return OcrFileMarkdownPagesOut(file_id=row.id, ocr_type=row.ocr_type, pages=pages)

