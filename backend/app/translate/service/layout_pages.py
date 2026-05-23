"""Assemble translate job layout-pages API from ``layout_snapshot_json``."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

_BLOCK_KEY_PAGE_RE = re.compile(r"^p(\d+)\.")

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
from app.translate.domain.constants import (
    DOC_TRANSLATE_STATUS_FAILED,
    DOC_TRANSLATE_STATUS_SUCCESS,
)
from app.translate.domain.db.models import DocTranslateJob, DocTranslateSegment
from app.translate.domain.dto import SegmentDraft
from app.layout.segments import segment_drafts_to_layout_document

_LOGGER = logging.getLogger(__name__)


def _page_index_from_block_key(block_key: str | None) -> int | None:
    """Parse ``p{n}.`` prefix from layout block keys."""

    if not block_key:
        return None
    match = _BLOCK_KEY_PAGE_RE.match(block_key)
    if match is None:
        return None
    return int(match.group(1))


def _normalize_segment_anchor(anchor: dict[str, Any], *, seq: int) -> dict[str, Any]:
    """Map legacy anchors (``page``, ``kind``) to LDM fields used for preview."""

    page_index = anchor.get("page_index")
    if page_index is None and "page" in anchor:
        page_index = int(anchor["page"])
    elif page_index is None:
        page_index = _page_index_from_block_key(
            str(anchor["block_key"]) if anchor.get("block_key") else None
        )
    if page_index is None:
        page_index = 0
    else:
        page_index = int(page_index)
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


def _segment_page_index(seg: DocTranslateSegment) -> int:
    """Resolve page index from segment anchor (supports legacy ``page`` and ``block_key``)."""

    anchor = seg.anchor_json if isinstance(seg.anchor_json, dict) else {}
    if "page_index" in anchor:
        return int(anchor["page_index"])
    if "page" in anchor:
        return int(anchor["page"])
    if "sheet_index" in anchor:
        return int(anchor["sheet_index"])
    parsed = _page_index_from_block_key(
        str(anchor["block_key"]) if anchor.get("block_key") else None
    )
    if parsed is not None:
        return parsed
    return 0


def _segments_on_page(segments: list[DocTranslateSegment], page_index: int) -> list[DocTranslateSegment]:
    """Return segments belonging to one page, ordered by ``seq``."""

    return sorted(
        [s for s in segments if _segment_page_index(s) == page_index],
        key=lambda s: s.seq,
    )


def _page_markdown_from_segments(
    segments_on_page: list[DocTranslateSegment],
    *,
    use_translation: bool,
    preserve_untranslated_slots: bool = True,
    pending_placeholder: str = "",
) -> str:
    """Build page markdown from persisted segments (aligned source vs translation columns)."""

    pieces: list[str] = []
    for seg in segments_on_page:
        anchor = seg.anchor_json if isinstance(seg.anchor_json, dict) else {}
        if use_translation:
            if anchor.get("skip_translate"):
                text = seg.source_text
            elif seg.translated_text is not None and seg.translated_text.strip():
                text = seg.translated_text
            elif preserve_untranslated_slots:
                text = pending_placeholder
            else:
                continue
        else:
            text = seg.source_text
        text = (text or "").strip()
        if use_translation and preserve_untranslated_slots and not text:
            pieces.append("")
        elif text:
            pieces.append(text)
    return "\n\n".join(pieces)


def _source_markdown_for_page(page: LayoutPage, segments_on_page: list[DocTranslateSegment]) -> str:
    """Build source column markdown; segments are authoritative when present."""

    if segments_on_page:
        return _page_markdown_from_segments(segments_on_page, use_translation=False)
    return page_markdown(page, use_translation=False)


def _all_page_indices(doc: LayoutDocument, segments: list[DocTranslateSegment]) -> list[int]:
    """Page list for preview: segment pages only when segments exist, else layout pages."""

    if segments:
        return sorted({_segment_page_index(s) for s in segments})
    return sorted(p.page_index for p in doc.pages)


def _layout_page_at(doc: LayoutDocument, page_index: int) -> LayoutPage:
    """Return the layout page for ``page_index``, or an empty placeholder page."""

    for page in doc.pages:
        if page.page_index == page_index:
            return page
    return LayoutPage(page_index=page_index, blocks=[])


def _apply_segment_translations(doc: LayoutDocument, segments: list[DocTranslateSegment]) -> LayoutDocument:
    """Merge translated segment text into blocks by ``block_key`` and all ``sub_index`` values."""

    by_block: dict[str, dict[int, str]] = {}
    for seg in segments:
        if not isinstance(seg.anchor_json, dict):
            continue
        key, sub = _translation_key(seg.anchor_json, seq=seg.seq)
        if seg.translated_text is not None:
            by_block.setdefault(key, {})[sub] = seg.translated_text

    new_pages: list[LayoutPage] = []
    for page in doc.pages:
        new_blocks: list[LayoutBlock] = []
        for block in page.blocks:
            if block.skip_translate:
                translated = block.source_text
            else:
                subs = by_block.get(block.block_key, {})
                if not subs:
                    translated = None
                else:
                    translated = "\n\n".join(subs[i] for i in sorted(subs))
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
    job_terminal = job.status in (DOC_TRANSLATE_STATUS_SUCCESS, DOC_TRANSLATE_STATUS_FAILED)
    pending_placeholder = "" if job_terminal else "…"

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
    for page_index in _all_page_indices(doc, segment_list):
        page = _layout_page_at(doc, page_index)
        segments_on_page = _segments_on_page(segment_list, page_index)
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
                source_markdown=_source_markdown_for_page(page, segments_on_page),
                translated_markdown=_page_markdown_from_segments(
                    segments_on_page,
                    use_translation=True,
                    preserve_untranslated_slots=True,
                    pending_placeholder=pending_placeholder,
                ),
                images=images_by_page.get(page.page_index),
            )
        )

    return OcrLayoutPagesOut(
        file_id=job.id,
        ocr_type=job.file_ext or "translate",
        layout_version=settings.layout_schema_version,
        pages=out_pages,
    )
