"""Tests for OCR-to-translate extract fallback when LDM blocks are missing."""

from __future__ import annotations

from pathlib import Path

from app.translate.service.strategies.pdf_strategy import PdfTranslateStrategy


def test_pdf_extract_uses_ocr_pages_when_layout_missing() -> None:
    """Scanned PDF path must consume OCR markdown when ``layout_document`` is None."""

    strategy = PdfTranslateStrategy()
    drafts = strategy.extract(
        Path("scan.pdf"),
        layout_document=None,
        ocr_pages=[(0, "# Title\n\nParagraph one."), (1, "Page two text.")],
    )
    assert len(drafts) >= 2
    assert any("Title" in d.source_text for d in drafts)
    assert all(d.anchor_json.get("kind") == "ocr_page" for d in drafts)
