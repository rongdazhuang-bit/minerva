"""PDF document translation strategy with optional OCR page text."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import ClassVar

import fitz

from app.layout.models import LayoutDocument
from app.layout.segments import layout_to_segment_drafts
from app.layout.writers.base import WriteContext
from app.layout.writers.pdf_writer import PdfWriter
from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy

_PDF_MIN_TEXT_CHARS = 32
# PyMuPDF ``blocks`` on the same visual row (points).
_LINE_Y_TOLERANCE = 8
# When many blocks are very short, the text layer is usually formula/layout spans.
_FRAGMENTED_MIN_BLOCKS = 20
_FRAGMENTED_SHORT_MAX_LEN = 35
_FRAGMENTED_SHORT_RATIO = 0.55

_MATH_SYMBOL_RE = re.compile(r"[∫∑Σ∂∇√∞±≤≥≠≈^_{}\\]")


def _collect_pdf_block_texts(doc: fitz.Document) -> list[str]:
    """Return non-empty text from every PyMuPDF block across pages."""

    texts: list[str] = []
    for page in doc:
        for block in page.get_text("blocks"):
            if len(block) < 5:
                continue
            text = str(block[4]).strip()
            if text:
                texts.append(text)
    return texts


def pdf_text_layer_is_fragmented(block_texts: list[str]) -> bool:
    """Detect PDFs whose text layer is many tiny positioned spans (typical for formula PDFs)."""

    n = len(block_texts)
    if n < _FRAGMENTED_MIN_BLOCKS:
        return False
    short_count = sum(1 for t in block_texts if len(t) <= _FRAGMENTED_SHORT_MAX_LEN)
    return short_count / n >= _FRAGMENTED_SHORT_RATIO


def is_formula_like_text(text: str) -> bool:
    """Heuristic: short or symbol-heavy lines are treated as formulas on native PDF extract."""

    stripped = text.strip()
    if not stripped:
        return False
    symbol_hits = len(_MATH_SYMBOL_RE.findall(stripped))
    if len(stripped) <= 16 and symbol_hits >= 1:
        return True
    if len(stripped) <= 120 and symbol_hits >= 3:
        return True
    return False


def _join_line_parts(parts: list[tuple[list[float], str]]) -> tuple[list[float], str]:
    """Merge bbox union and joined text for blocks on one visual line."""

    bbox = [
        min(p[0][0] for p in parts),
        min(p[0][1] for p in parts),
        max(p[0][2] for p in parts),
        max(p[0][3] for p in parts),
    ]
    text = " ".join(p[1] for p in parts)
    return bbox, text


def merge_page_text_blocks(page: fitz.Page) -> list[tuple[list[float], str]]:
    """Merge PyMuPDF text blocks on the same visual row into one segment."""

    rows: list[tuple[float, float, list[float], str]] = []
    for block in page.get_text("blocks"):
        if len(block) < 5:
            continue
        text = str(block[4]).strip()
        if not text:
            continue
        y0, x0 = float(block[1]), float(block[0])
        bbox = [float(block[0]), float(block[1]), float(block[2]), float(block[3])]
        rows.append((y0, x0, bbox, text))
    rows.sort(key=lambda r: (round(r[0] / _LINE_Y_TOLERANCE), r[1]))

    merged: list[tuple[list[float], str]] = []
    line_y: float | None = None
    line_parts: list[tuple[list[float], str]] = []
    for y0, _x0, bbox, text in rows:
        if line_y is not None and abs(y0 - line_y) <= _LINE_Y_TOLERANCE:
            line_parts.append((bbox, text))
        else:
            if line_parts:
                merged.append(_join_line_parts(line_parts))
            line_y = y0
            line_parts = [(bbox, text)]
    if line_parts:
        merged.append(_join_line_parts(line_parts))
    return merged


class PdfTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.pdf`` text layers or OCR-derived page markdown."""

    extensions: ClassVar[frozenset[str]] = frozenset({"pdf"})

    def needs_ocr(self, local_path: Path) -> bool:
        """Use OCR when the PDF has almost no text or a fragmented formula-style text layer."""

        doc = fitz.open(local_path)
        try:
            block_texts = _collect_pdf_block_texts(doc)
            total = sum(len(t) for t in block_texts)
            if total < _PDF_MIN_TEXT_CHARS:
                return True
            return pdf_text_layer_is_fragmented(block_texts)
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
        drafts: list[SegmentDraft] = []
        seq = 0
        try:
            for page_no, page in enumerate(doc):
                for bbox, text in merge_page_text_blocks(page):
                    skip = is_formula_like_text(text)
                    drafts.append(
                        SegmentDraft(
                            seq=seq,
                            source_text=text,
                            anchor_json={
                                "kind": "text_block",
                                "page": page_no,
                                "page_index": page_no,
                                "bbox": bbox,
                                "label": "formula" if skip else "text",
                                "skip_translate": skip,
                            },
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
        PdfWriter().write(
            WriteContext(source_path=source_path, out_path=out_path, segments=segments)
        )


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
