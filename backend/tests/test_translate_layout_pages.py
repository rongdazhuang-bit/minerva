"""Translate layout-pages fallback from legacy segment anchors."""

from app.translate.domain.db.models import DocTranslateSegment
from app.layout.models import LayoutBlock, LayoutDocument, LayoutPage
from app.translate.service.layout_pages import (
    _all_page_indices,
    _layout_document_from_segments,
    _normalize_segment_anchor,
    _page_markdown_from_segments,
    _segment_page_index,
    _segments_on_page,
    _source_markdown_for_page,
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


def test_page_markdown_from_segments_uses_translation_not_source() -> None:
    """Translated page markdown must not fall back to English source text."""

    segments = [
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=0,
            source_text="Abstract",
            translated_text="摘要",
            status="DONE",
            anchor_json={"page_index": 0, "block_key": "p0.b0", "sub_index": 0},
            error_message=None,
        ),
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=1,
            source_text="Abbreviations",
            translated_text=None,
            status="DONE",
            anchor_json={"page_index": 0, "block_key": "p0.b1", "sub_index": 0},
            error_message=None,
        ),
    ]
    on_page = _segments_on_page(segments, 0)
    translated_md = _page_markdown_from_segments(
        on_page,
        use_translation=True,
        preserve_untranslated_slots=False,
    )
    assert "摘要" in translated_md
    assert "Abstract" not in translated_md
    assert "Abbreviations" not in translated_md


def test_page_markdown_preserves_untranslated_slots() -> None:
    """Preview keeps one paragraph slot per segment while translation is in progress."""

    segments = [
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=0,
            source_text="Done",
            translated_text="完成",
            status="DONE",
            anchor_json={"page_index": 0, "block_key": "p0.b0", "sub_index": 0},
            error_message=None,
        ),
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=1,
            source_text="Pending",
            translated_text=None,
            status="PENDING",
            anchor_json={"page_index": 0, "block_key": "p0.b1", "sub_index": 0},
            error_message=None,
        ),
    ]
    on_page = _segments_on_page(segments, 0)
    translated_md = _page_markdown_from_segments(
        on_page,
        use_translation=True,
        pending_placeholder="",
    )
    assert translated_md.split("\n\n") == ["完成", ""]


def test_all_page_indices_includes_segment_only_pages() -> None:
    """Pages referenced only by segments are still returned in layout-pages."""

    doc = LayoutDocument(
        pages=[LayoutPage(page_index=0, blocks=[])],
        layout_source="ocr",
    )
    segments = [
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=0,
            source_text="p2",
            translated_text=None,
            status="PENDING",
            anchor_json={"page_index": 2, "block_key": "p2.b0", "sub_index": 0},
            error_message=None,
        ),
    ]
    assert _all_page_indices(doc, segments) == [2]


def test_segment_page_index_from_block_key() -> None:
    """Infer page number from ``p{n}.`` block keys when anchor omits page fields."""

    seg = DocTranslateSegment(
        id=None,  # type: ignore[arg-type]
        job_id=None,  # type: ignore[arg-type]
        workspace_id=None,  # type: ignore[arg-type]
        seq=3,
        source_text="Body",
        translated_text=None,
        status="PENDING",
        anchor_json={"block_key": "p4.b2", "sub_index": 0},
        error_message=None,
    )
    assert _segment_page_index(seg) == 4


def test_source_markdown_uses_segments_only() -> None:
    """When segments exist, do not append duplicate layout block markdown."""

    page = LayoutPage(
        page_index=0,
        blocks=[
            LayoutBlock(
                block_key="p0.b0",
                label="text",
                reading_order=0,
                source_text="From segment",
            ),
            LayoutBlock(
                block_key="p0.b99",
                label="text",
                reading_order=1,
                source_text="Orphan block",
            ),
        ],
    )
    segments = [
        DocTranslateSegment(
            id=None,  # type: ignore[arg-type]
            job_id=None,  # type: ignore[arg-type]
            workspace_id=None,  # type: ignore[arg-type]
            seq=0,
            source_text="From segment",
            translated_text=None,
            status="PENDING",
            anchor_json={"page_index": 0, "block_key": "p0.b0", "sub_index": 0},
            error_message=None,
        ),
    ]
    md = _source_markdown_for_page(page, _segments_on_page(segments, 0))
    assert md == "From segment"
    assert "Orphan block" not in md
