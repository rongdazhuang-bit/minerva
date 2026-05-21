"""Assemble translate job layout-pages API from ``layout_snapshot_json``."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import AppError
from app.file_ocr.api.schemas import LayoutBlockOut, OcrLayoutPageOut, OcrLayoutPagesOut
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.file_ocr.service.markdown_pages import _parse_markdown_images
from app.layout.load_ocr import load_layout_document_from_ocr_file
from app.layout.models import LayoutBlock, LayoutDocument, LayoutPage
from app.layout.to_markdown import page_markdown
from app.s3.service.s3_file_service import S3FileService
from app.translate.domain.db.models import DocTranslateJob, DocTranslateSegment
from app.translate.domain.dto import SegmentDraft
from app.layout.segments import segment_drafts_to_layout_document

_LOGGER = logging.getLogger(__name__)


def _normalize_segment_anchor(anchor: dict[str, Any], *, seq: int) -> dict[str, Any]:
    """Map legacy anchors (``page``, ``kind``) to LDM fields used for preview."""

    page_index = anchor.get("page_index")
    if page_index is None and "page" in anchor:
        page_index = int(anchor["page"])
    else:
        page_index = int(page_index or 0)
    block_key = anchor.get("block_key")
    if not block_key:
        if "block" in anchor:
            block_key = f"p{page_index}.b{anchor['block']}"
        else:
            block_key = f"p{page_index}.seg{seq}"
    return {
        **anchor,
        "page_index": page_index,
        "block_key": str(block_key),
        "label": str(anchor.get("label", "text")),
        "overflow_policy": anchor.get("overflow_policy", "shrink"),
        "skip_translate": bool(anchor.get("skip_translate", False)),
    }


def _translation_key(anchor: dict[str, Any], *, seq: int) -> tuple[str, int]:
    """Return ``(block_key, sub_index)`` for merging segment translations into blocks."""

    normalized = _normalize_segment_anchor(anchor, seq=seq)
    return str(normalized["block_key"]), int(normalized.get("sub_index", 0))


def _layout_document_from_snapshot(raw: object | None) -> LayoutDocument | None:
    """Parse ``layout_snapshot_json`` into a ``LayoutDocument``."""

    if not isinstance(raw, dict):
        return None
    pages_raw = raw.get("pages")
    if not isinstance(pages_raw, list):
        return None
    try:
        return LayoutDocument.model_validate(raw)
    except Exception:
        return None


def _layout_document_from_segments(segments: list[DocTranslateSegment]) -> LayoutDocument | None:
    """Rebuild a minimal LDM from persisted segments when no snapshot was stored."""

    if not segments:
        return None
    drafts: list[SegmentDraft] = []
    for seg in segments:
        anchor = seg.anchor_json if isinstance(seg.anchor_json, dict) else {}
        drafts.append(
            SegmentDraft(
                seq=seg.seq,
                source_text=seg.source_text,
                anchor_json=_normalize_segment_anchor(anchor, seq=seg.seq),
            )
        )
    layout_source = "native"
    if any(isinstance(s.anchor_json, dict) and s.anchor_json.get("kind") == "ocr_page" for s in segments):
        layout_source = "ocr"
    return segment_drafts_to_layout_document(drafts, layout_source=layout_source)


def _apply_segment_translations(doc: LayoutDocument, segments: list[DocTranslateSegment]) -> LayoutDocument:
    """Merge translated segment text into blocks by ``block_key`` and ``sub_index``."""

    by_key: dict[tuple[str, int], str] = {}
    for seg in segments:
        if not isinstance(seg.anchor_json, dict):
            continue
        key, sub = _translation_key(seg.anchor_json, seq=seg.seq)
        if seg.translated_text is not None:
            by_key[(key, sub)] = seg.translated_text

    new_pages: list[LayoutPage] = []
    for page in doc.pages:
        new_blocks: list[LayoutBlock] = []
        for block in page.blocks:
            translated = by_key.get((block.block_key, 0))
            if block.skip_translate:
                translated = block.source_text
            new_blocks.append(block.model_copy(update={"translated_text": translated}))
        new_pages.append(page.model_copy(update={"blocks": new_blocks}))
    return doc.model_copy(update={"pages": new_pages})


async def get_translate_job_layout_pages(
    *,
    session: AsyncSession,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> OcrLayoutPagesOut:
    """Build layout-pages payload for one translation job."""

    job = (
        await session.execute(
            select(DocTranslateJob).where(
                DocTranslateJob.id == job_id,
                DocTranslateJob.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise AppError("translate.job_not_found", "翻译任务不存在。", 404)

    doc = _layout_document_from_snapshot(job.layout_snapshot_json)
    segments = (
        await session.execute(
            select(DocTranslateSegment)
            .where(
                DocTranslateSegment.job_id == job_id,
                DocTranslateSegment.workspace_id == workspace_id,
            )
            .order_by(DocTranslateSegment.seq.asc())
        )
    ).scalars().all()
    segment_list = list(segments)

    if doc is None and job.ocr_file_id:
        doc = await load_layout_document_from_ocr_file(
            session, workspace_id=workspace_id, ocr_file_id=job.ocr_file_id
        )
    if doc is None:
        doc = _layout_document_from_segments(segment_list)
    if doc is None:
        raise AppError("layout.blocks_missing", "No layout snapshot for this job.", 404)

    doc = _apply_segment_translations(doc, segment_list)

    raster_by_page: dict[int, str | None] = {}
    images_by_page: dict[int, dict[str, str] | None] = {}
    if job.ocr_file_id:
        paddle_rows = (
            await session.execute(
                select(OcrFilePaddleocr).where(
                    OcrFilePaddleocr.workspace_id == workspace_id,
                    OcrFilePaddleocr.file_id == job.ocr_file_id,
                )
            )
        ).scalars().all()
        for pr in paddle_rows:
            idx = int(pr.page_index or 0)
            raster_by_page[idx] = pr.page_raster_object_key
            images_by_page[idx] = _parse_markdown_images(pr.markdown_images)

    s3 = S3FileService(session=session)
    out_pages: list[OcrLayoutPageOut] = []
    for page in sorted(doc.pages, key=lambda p: p.page_index):
        page_raster_url = None
        key = raster_by_page.get(page.page_index)
        if key:
            try:
                redirect = await s3.get_download_redirect(
                    workspace_id=workspace_id, object_key=key, presign_expires_in=600
                )
                page_raster_url = redirect.url
            except Exception:
                _LOGGER.warning("translate layout raster presign failed job=%s", job_id)

        blocks_out = [
            LayoutBlockOut(
                block_key=b.block_key,
                label=b.label,
                source_text=b.source_text,
                bbox=b.bbox,
                overflow_policy=b.overflow_policy,
                skip_translate=b.skip_translate,
            )
            for b in page.blocks
        ]
        out_pages.append(
            OcrLayoutPageOut(
                page_index=page.page_index,
                width=page.width,
                height=page.height,
                blocks=blocks_out,
                page_raster_url=page_raster_url,
                source_markdown=page_markdown(page, use_translation=False),
                translated_markdown=page_markdown(page, use_translation=True),
                images=images_by_page.get(page.page_index),
            )
        )

    return OcrLayoutPagesOut(
        file_id=job.id,
        ocr_type=job.file_ext or "translate",
        layout_version=settings.layout_schema_version,
        pages=out_pages,
    )
