"""Regression tests for translate layout-pages fallback assembly."""

from app.translate.domain.db.models import DocTranslateSegment
from app.translate.service.layout_pages import _layout_document_from_segments


def test_layout_document_from_segments_uses_legacy_page_anchor() -> None:
    """Fallback LDM preserves legacy ``page`` and ``block`` segment anchors."""

    seg = DocTranslateSegment(
        seq=0,
        source_text="Hello",
        translated_text="你好",
        status="DONE",
        anchor_json={"page": 2, "block": 3},
    )

    doc = _layout_document_from_segments([seg])

    assert doc is not None
    assert doc.pages[0].page_index == 2
    assert doc.pages[0].blocks[0].block_key == "p2.b3"
