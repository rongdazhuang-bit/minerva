"""Load ``LayoutDocument`` and markdown fallbacks from persisted OCR page rows."""

from __future__ import annotations

import uuid

from sqlalchemy import asc, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.file_ocr.service.result_read.registry import get_file_ocr_result_read_strategy
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
    if not rows or all(
        r.layout_blocks_json is None
        or (isinstance(r.layout_blocks_json, list) and len(r.layout_blocks_json) == 0)
        for r in rows
    ):
        return None
    pages: list[LayoutPage] = []
    for r in rows:
        if not isinstance(r.layout_blocks_json, list) or len(r.layout_blocks_json) == 0:
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


async def load_ocr_markdown_pages_for_translate(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
) -> list[tuple[int, str]]:
    """Return ordered ``(page_index, markdown_text)`` when LDM blocks are unavailable."""

    ocr_row = (
        await session.execute(
            select(OcrFile).where(
                OcrFile.id == ocr_file_id,
                OcrFile.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if ocr_row is None:
        return []
    try:
        read_strategy = get_file_ocr_result_read_strategy(ocr_row.ocr_type)
    except KeyError:
        return []
    raw_pages = await read_strategy.load_pages(
        session=session,
        workspace_id=workspace_id,
        file_id=ocr_file_id,
    )
    out: list[tuple[int, str]] = []
    for idx, page in enumerate(raw_pages):
        text = (page.markdown_text or "").strip()
        if not text:
            continue
        page_no = int(page.page_index if page.page_index is not None else idx)
        out.append((page_no, page.markdown_text or ""))
    return out
