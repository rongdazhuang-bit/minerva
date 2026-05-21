"""Translate layout-pages fallback from legacy segment anchors."""

from app.translate.domain.db.models import DocTranslateSegment
from app.translate.service.layout_pages import (
    _layout_document_from_segments,
    _normalize_segment_anchor,
)


def test_normalize_legacy_pdf_anchor() -> None:
    """Legacy PDF anchors use ``page`` instead of ``page_index``."""

    out = _normalize_segment_anchor(
        {"kind": "text_block", "page": 2, "bbox": [0.0, 1.0, 2.0, 3.0]},
        seq=5,
    )
    assert out["page_index"] == 2
    assert out["block_key"] == "p2.seg5"


def test_layout_document_from_legacy_segments() -> None:
    """Jobs without ``layout_snapshot_json`` can still serve layout-pages."""

    segments = [
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=0,
            source_text="Hello",
            translated_text="你好",
            status="DONE",
            anchor_json={"kind": "text_block", "page": 0, "bbox": [1.0, 2.0, 3.0, 4.0]},
            error_message=None,
        ),
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=1,
            source_text="World",
            translated_text="世界",
            status="DONE",
            anchor_json={"kind": "text_block", "page": 0, "bbox": [5.0, 6.0, 7.0, 8.0]},
            error_message=None,
        ),
    ]
    doc = _layout_document_from_segments(segments)
    assert doc is not None
    assert len(doc.pages) == 1
    assert doc.pages[0].page_index == 0
    assert len(doc.pages[0].blocks) == 2
