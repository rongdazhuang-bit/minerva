"""Regression tests for translate layout-pages fallback assembly."""

from app.layout.segments import segment_drafts_to_layout_document
from app.translate.domain.dto import SegmentDraft
from app.translate.domain.db.models import DocTranslateSegment
from app.translate.service.layout_pages import _layout_document_from_segments, _segment_page_index


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


def test_layout_document_from_segments_uses_legacy_sheet_index_pages() -> None:
    """Fallback LDM preserves legacy spreadsheet sheet indices as pages."""

    first = DocTranslateSegment(
        seq=0,
        source_text="Sheet one",
        translated_text="表一",
        status="DONE",
        anchor_json={"sheet_index": 0, "sheet": "S1", "row": 0, "col": 0},
    )
    second = DocTranslateSegment(
        seq=1,
        source_text="Sheet two",
        translated_text="表二",
        status="DONE",
        anchor_json={"sheet_index": 1, "sheet": "S2", "row": 0, "col": 0},
    )

    doc = _layout_document_from_segments([first, second])

    assert doc is not None
    assert [page.page_index for page in doc.pages] == [0, 1]
    assert doc.pages[1].blocks[0].source_text == "Sheet two"
    assert doc.pages[1].blocks[0].sheet_name == "S2"


def test_segment_drafts_to_layout_document_uses_legacy_page_block_anchor() -> None:
    """Build LDM pages from legacy OCR anchors using ``page`` and ``block``."""

    draft = SegmentDraft(
        seq=7,
        source_text="Hello",
        anchor_json={"page": 2, "block": 3},
    )

    doc = segment_drafts_to_layout_document([draft], layout_source="ocr")

    assert doc.pages[0].page_index == 2
    assert doc.pages[0].blocks[0].block_key == "p2.b3"


def test_segment_page_index_uses_legacy_sheet_index_anchor() -> None:
    """Resolve group-by-page indices from legacy spreadsheet ``sheet_index`` anchors."""

    seg = DocTranslateSegment(
        seq=0,
        source_text="Hello",
        translated_text="你好",
        status="DONE",
        anchor_json={"sheet": "Sheet2", "sheet_index": 1},
    )

    assert _segment_page_index(seg) == 1
