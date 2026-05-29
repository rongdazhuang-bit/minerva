"""Tests for MinerU ZIP/JSON response parsing."""

from __future__ import annotations

from pathlib import Path

from app.file_ocr.service.mineru_result_parse import parse_mineru_zip_bytes

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mineru" / "sample.zip"


def test_parse_mineru_zip_single_page() -> None:
    """ZIP with middle.json yields one page with markdown and data-uri image."""
    raw = FIXTURE.read_bytes()
    pages = parse_mineru_zip_bytes(raw)
    assert len(pages) == 1
    assert pages[0].page_index == 0
    assert "Hello" in (pages[0].markdown_text or "")
    assert pages[0].page_width == 595
    assert pages[0].page_height == 842
    images = pages[0].markdown_images or {}
    assert "demo/images/p0.png" in images
    assert images["demo/images/p0.png"].startswith("data:image/")
