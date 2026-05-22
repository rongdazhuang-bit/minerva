"""Render layout blocks into page-level Markdown for OCR/translate preview."""

from __future__ import annotations

import re

from app.layout.models import LayoutBlock, LayoutDocument, LayoutPage

_HTML_DIV_RE = re.compile(r"^\s*<div[^>]*>\s*</div>\s*$", re.IGNORECASE)


def _block_markdown_piece(block: LayoutBlock, *, use_translation: bool) -> str:
    """Format one block as a Markdown fragment."""

    if block.label == "figure" and _HTML_DIV_RE.match(block.source_text or ""):
        return ""
    if block.skip_translate or not use_translation:
        text = block.source_text
    elif block.translated_text is not None and str(block.translated_text).strip():
        text = block.translated_text
    elif use_translation:
        text = ""
    else:
        text = block.source_text
    text = (text or "").strip()
    if not text:
        return ""
    if block.label == "title" and not text.startswith("#"):
        return f"## {text}"
    return text


def page_markdown(page: LayoutPage, *, use_translation: bool = False) -> str:
    """Join ordered blocks on one page into a single Markdown string."""

    pieces: list[str] = []
    for block in sorted(page.blocks, key=lambda b: b.reading_order):
        piece = _block_markdown_piece(block, use_translation=use_translation)
        if piece:
            pieces.append(piece)
    return "\n\n".join(pieces)


def document_markdown(doc: LayoutDocument, *, use_translation: bool = False) -> str:
    """Join all pages into one Markdown document."""

    parts = [
        page_markdown(page, use_translation=use_translation)
        for page in sorted(doc.pages, key=lambda p: p.page_index)
    ]
    return "\n\n".join(p for p in parts if p.strip())
