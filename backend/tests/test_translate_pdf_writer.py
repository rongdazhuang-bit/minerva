"""Tests for PDF layout writer behavior."""

from pathlib import Path

import fitz

from app.layout.writers.base import WriteContext
from app.layout.writers.pdf_writer import PdfWriter
from app.translate.domain.dto import SegmentRecord


def test_pdf_writer_skips_formula_blocks(tmp_path: Path) -> None:
    """Formula anchors marked as skipped should keep translated text out of output."""

    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "E=mc^2")
    doc.save(source)
    doc.close()

    PdfWriter().write(
        WriteContext(
            source_path=source,
            out_path=output,
            segments=[
                SegmentRecord(
                    seq=0,
                    source_text="E=mc^2",
                    translated_text="should not appear",
                    anchor_json={
                        "page": 0,
                        "bbox": [70, 55, 180, 90],
                        "skip_translate": True,
                        "label": "formula",
                    },
                )
            ],
        )
    )

    out = fitz.open(output)
    try:
        text = "\n".join(page.get_text() for page in out)
    finally:
        out.close()
    assert "should not appear" not in text
