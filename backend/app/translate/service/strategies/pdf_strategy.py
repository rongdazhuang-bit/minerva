"""PDF document translation strategy with optional OCR page text."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import ClassVar

import fitz

from app.layout.models import LayoutDocument
from app.layout.segments import layout_to_segment_drafts
from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy

_PDF_MIN_TEXT_CHARS = 32


class PdfTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.pdf`` text layers or OCR-derived page markdown."""

    extensions: ClassVar[frozenset[str]] = frozenset({"pdf"})

    def needs_ocr(self, local_path: Path) -> bool:
        doc = fitz.open(local_path)
        try:
            total = 0
            for page in doc:
                total += len((page.get_text() or "").strip())
                if total >= _PDF_MIN_TEXT_CHARS:
                    return False
            return True
        finally:
            doc.close()

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
        layout_document: LayoutDocument | None = None,
    ) -> list[SegmentDraft]:
        if layout_document is not None:
            return layout_to_segment_drafts(layout_document)
        if ocr_pages:
            drafts: list[SegmentDraft] = []
            seq = 0
            for page_no, md in ocr_pages:
                for block in _split_ocr_markdown_blocks(md):
                    if not block.strip():
                        continue
                    drafts.append(
                        SegmentDraft(
                            seq=seq,
                            source_text=block,
                            anchor_json={"kind": "ocr_page", "page": page_no, "block": seq},
                        )
                    )
                    seq += 1
            return drafts

        doc = fitz.open(local_path)
        drafts = []
        seq = 0
        try:
            for page_no, page in enumerate(doc):
                blocks = page.get_text("blocks")
                for b in blocks:
                    if len(b) < 5:
                        continue
                    text = str(b[4]).strip()
                    if not text:
                        continue
                    bbox = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
                    drafts.append(
                        SegmentDraft(
                            seq=seq,
                            source_text=text,
                            anchor_json={"kind": "text_block", "page": page_no, "bbox": bbox},
                        )
                    )
                    seq += 1
        finally:
            doc.close()
        return drafts

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        doc = fitz.open(source_path)
        try:
            for seg in segments:
                anchor = seg.anchor_json or {}
                page_no = int(anchor.get("page", 0))
                if page_no >= len(doc):
                    continue
                page = doc[page_no]
                bbox = anchor.get("bbox")
                if isinstance(bbox, list) and len(bbox) >= 4:
                    rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
                    page.add_redact_annot(rect, text="")
                    page.apply_redactions()
                    page.insert_textbox(
                        rect,
                        seg.translated_text or "",
                        fontsize=10,
                        align=fitz.TEXT_ALIGN_LEFT,
                    )
                elif anchor.get("skip_translate"):
                    continue
                else:
                    page.insert_text((72, 72 + (seg.seq % 40) * 14), seg.translated_text or "")
            doc.save(out_path)
        finally:
            doc.close()


def _split_ocr_markdown_blocks(md: str) -> list[str]:
    """Split OCR markdown into paragraph-sized blocks."""

    parts: list[str] = []
    buf: list[str] = []
    for line in md.splitlines():
        if line.strip() == "":
            if buf:
                parts.append("\n".join(buf))
                buf = []
        else:
            buf.append(line)
    if buf:
        parts.append("\n".join(buf))
    return parts if parts else ([md] if md.strip() else [])
