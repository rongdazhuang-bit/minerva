"""Assemble markdown-pages API payload for SUCCESS ``ocr_file`` rows."""

from __future__ import annotations

from app.core.log import get_logger
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.file_ocr.api.schemas import OcrFileMarkdownPageOut, OcrFileMarkdownPagesOut
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.file_ocr.service.result_read.registry import get_file_ocr_result_read_strategy
from app.layout.serialize import layout_page_from_blocks_json
from app.layout.to_markdown import page_markdown
from sqlalchemy import asc, nullslast, select

log = get_logger(__name__)


def _parse_markdown_images(raw: str | None) -> dict[str, str] | None:
    """Parse ``markdown_images`` JSON text into a ``str -> str`` map, or ``None`` if invalid."""

    if raw is None or str(raw).strip() == "":
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("markdown_images JSON decode failed for OCR result page")
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, str):
            log.warning("markdown_images contains non-string key or value")
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
    derived_by_index: dict[int, str] = {}
    if row.ocr_type == "PADDLE_OCR":
        paddle_rows = (
            await session.execute(
                select(OcrFilePaddleocr)
                .where(
                    OcrFilePaddleocr.workspace_id == workspace_id,
                    OcrFilePaddleocr.file_id == ocr_file_id,
                )
                .order_by(nullslast(asc(OcrFilePaddleocr.page_index)), asc(OcrFilePaddleocr.id))
            )
        ).scalars().all()
        for pr in paddle_rows:
            if pr.layout_blocks_json and isinstance(pr.layout_blocks_json, list):
                layout_page = layout_page_from_blocks_json(
                    page_index=int(pr.page_index or 0),
                    width=pr.page_width,
                    height=pr.page_height,
                    blocks_json=pr.layout_blocks_json,
                )
                derived_by_index[int(pr.page_index or 0)] = page_markdown(
                    layout_page, use_translation=False
                )

    pages = []
    for p in raw_pages:
        idx = int(p.page_index or 0)
        md_text = derived_by_index.get(idx, p.markdown_text)
        pages.append(
            OcrFileMarkdownPageOut(
                page_index=p.page_index,
                markdown_text=md_text,
                images=_parse_markdown_images(p.markdown_images),
            )
        )
    return OcrFileMarkdownPagesOut(file_id=row.id, ocr_type=row.ocr_type, pages=pages)

