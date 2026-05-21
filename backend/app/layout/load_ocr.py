"""Load ``LayoutDocument`` from persisted OCR page rows."""

from __future__ import annotations

import uuid

from sqlalchemy import asc, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.layout.models import LayoutDocument, LayoutPage
from app.layout.serialize import layout_page_from_blocks_json


async def load_layout_document_from_ocr_file(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
) -> LayoutDocument | None:
    """Rebuild LDM from ``ocr_file_paddleocr`` rows when layout JSON exists."""

    stmt = (
        select(OcrFilePaddleocr)
        .where(
            OcrFilePaddleocr.workspace_id == workspace_id,
            OcrFilePaddleocr.file_id == ocr_file_id,
        )
        .order_by(nullslast(asc(OcrFilePaddleocr.page_index)), asc(OcrFilePaddleocr.id))
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows or all(r.layout_blocks_json is None for r in rows):
        return None
    pages: list[LayoutPage] = []
    for r in rows:
        if not isinstance(r.layout_blocks_json, list):
            continue
        pages.append(
            layout_page_from_blocks_json(
                page_index=int(r.page_index or 0),
                width=r.page_width,
                height=r.page_height,
                blocks_json=r.layout_blocks_json,
            )
        )
    if not pages:
        return None
    return LayoutDocument(pages=pages, layout_source="ocr")
