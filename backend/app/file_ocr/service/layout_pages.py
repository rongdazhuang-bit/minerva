"""Assemble layout-pages API payload for SUCCESS ``ocr_file`` rows."""

from __future__ import annotations

from app.core.log import get_logger
import json
import uuid

from sqlalchemy import asc, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import AppError
from app.file_ocr.api.schemas import LayoutBlockOut, OcrLayoutPageOut, OcrLayoutPagesOut
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.file_ocr.service.result_read.registry import get_file_ocr_result_read_strategy
from app.layout.serialize import layout_page_from_blocks_json
from app.layout.to_markdown import page_markdown
from app.s3.service.s3_file_service import S3FileService

log = get_logger(__name__)


def _parse_markdown_images(raw: str | None) -> dict[str, str] | None:
    """Parse ``markdown_images`` JSON text into a map."""

    if raw is None or str(raw).strip() == "":
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("markdown_images JSON decode failed for layout page")
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out if out else None


async def get_ocr_file_layout_pages(
    *,
    session: AsyncSession,
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
) -> OcrLayoutPagesOut:
    """Load per-page layout blocks and derived markdown for a SUCCESS OCR task."""

    result = await session.execute(
        select(OcrFile).where(OcrFile.id == ocr_file_id, OcrFile.workspace_id == workspace_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("ocr_file.not_found", "OCR task not found", 404)
    if row.status != "SUCCESS":
        raise AppError(
            "ocr_file.detail_requires_success",
            "Task must be SUCCESS to load layout pages",
            409,
        )
    if row.ocr_type != "PADDLE_OCR":
        try:
            get_file_ocr_result_read_strategy(row.ocr_type)
        except KeyError:
            raise AppError(
                "ocr_file.unsupported_detail_type",
                "OCR type does not support layout detail",
                422,
            ) from None
        raise AppError("layout.blocks_missing", "Layout pages not available for this OCR type yet.", 404)

    stmt = (
        select(OcrFilePaddleocr)
        .where(
            OcrFilePaddleocr.workspace_id == workspace_id,
            OcrFilePaddleocr.file_id == ocr_file_id,
        )
        .order_by(nullslast(asc(OcrFilePaddleocr.page_index)), asc(OcrFilePaddleocr.id))
    )
    db_pages = (await session.execute(stmt)).scalars().all()
    if not db_pages or all(p.layout_blocks_json is None for p in db_pages):
        raise AppError("layout.blocks_missing", "No layout blocks stored for this task.", 404)

    s3 = S3FileService(session=session)
    out_pages: list[OcrLayoutPageOut] = []
    for p in db_pages:
        page_index = int(p.page_index or 0)
        layout_page = layout_page_from_blocks_json(
            page_index=page_index,
            width=p.page_width,
            height=p.page_height,
            blocks_json=p.layout_blocks_json if isinstance(p.layout_blocks_json, list) else None,
        )
        page_raster_url: str | None = None
        if p.page_raster_object_key:
            try:
                redirect = await s3.get_download_redirect(
                    workspace_id=workspace_id,
                    object_key=p.page_raster_object_key,
                    presign_expires_in=600,
                )
                page_raster_url = redirect.url
            except Exception:
                log.warning("layout page raster presign failed file_id={} page={}", ocr_file_id, page_index)

        blocks_out = [
            LayoutBlockOut(
                block_key=b.block_key,
                label=b.label,
                source_text=b.source_text,
                bbox=b.bbox,
                overflow_policy=b.overflow_policy,
                skip_translate=b.skip_translate,
            )
            for b in layout_page.blocks
        ]
        out_pages.append(
            OcrLayoutPageOut(
                page_index=page_index,
                width=p.page_width,
                height=p.page_height,
                blocks=blocks_out,
                page_raster_url=page_raster_url,
                source_markdown=page_markdown(layout_page, use_translation=False),
                images=_parse_markdown_images(p.markdown_images),
            )
        )

    return OcrLayoutPagesOut(
        file_id=row.id,
        ocr_type=row.ocr_type,
        layout_version=settings.layout_schema_version,
        pages=out_pages,
    )
