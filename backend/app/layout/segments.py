"""Convert a layout document into translation segment drafts."""

from __future__ import annotations

from typing import Any, Literal

from app.layout.models import LayoutBlock, LayoutDocument, LayoutPage
from app.translate.domain.dto import SegmentDraft
from app.translate.service.text_segmentation import split_plain_text_into_segments

_DEFAULT_MAX_CHARS = 6000


def _anchor_for_block(block: LayoutBlock, *, sub_index: int = 0) -> dict[str, Any]:
    """Build ``anchor_json`` linking a segment back to one layout block."""

    anchor: dict[str, Any] = {
        "block_key": block.block_key,
        "sub_index": sub_index,
        "label": block.label,
        "overflow_policy": block.overflow_policy,
        "skip_translate": block.skip_translate,
    }
    if block.page_index is not None:
        anchor["page_index"] = block.page_index
    if block.bbox is not None:
        anchor["bbox"] = block.bbox
    if block.parent_key:
        anchor["parent_key"] = block.parent_key
    if block.table_grid:
        anchor["table_grid"] = block.table_grid
    if block.sheet_name:
        anchor["sheet_name"] = block.sheet_name
    return anchor


def _drafts_for_block(
    block: LayoutBlock,
    *,
    seq_start: int,
    max_chars: int,
) -> list[SegmentDraft]:
    """Expand one block into one or more segment drafts."""

    text = (block.source_text or "").strip()
    if not text and not block.skip_translate:
        return []
    if block.skip_translate or len(text) <= max_chars:
        return [
            SegmentDraft(
                seq=seq_start,
                source_text=block.source_text,
                anchor_json=_anchor_for_block(block, sub_index=0),
            )
        ]
    parts = split_plain_text_into_segments(text, max_chars=max_chars)
    drafts: list[SegmentDraft] = []
    for sub_idx, part in enumerate(parts):
        drafts.append(
            SegmentDraft(
                seq=seq_start + sub_idx,
                source_text=part,
                anchor_json=_anchor_for_block(block, sub_index=sub_idx),
            )
        )
    return drafts


def segment_drafts_to_layout_document(
    drafts: list[SegmentDraft],
    *,
    layout_source: Literal["native", "ocr", "hybrid"] = "native",
) -> LayoutDocument:
    """Build a minimal LDM snapshot from extract drafts for persistence and preview."""

    by_page: dict[int, list[LayoutBlock]] = {}
    for d in drafts:
        anchor = d.anchor_json or {}
        page_index = int(anchor.get("page_index", 0))
        block = LayoutBlock(
            block_key=str(anchor.get("block_key", f"p{page_index}.seg{d.seq}")),
            parent_key=anchor.get("parent_key"),
            label=str(anchor.get("label", "text")),
            reading_order=d.seq,
            source_text=d.source_text,
            bbox=anchor.get("bbox"),
            page_index=page_index,
            table_grid=anchor.get("table_grid"),
            overflow_policy=anchor.get("overflow_policy", "shrink"),
            skip_translate=bool(anchor.get("skip_translate", False)),
        )
        by_page.setdefault(page_index, []).append(block)
    pages = [
        LayoutPage(page_index=idx, blocks=sorted(blocks, key=lambda b: b.reading_order))
        for idx, blocks in sorted(by_page.items())
    ]
    return LayoutDocument(pages=pages, layout_source=layout_source)


def layout_to_segment_drafts(
    doc: LayoutDocument,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> list[SegmentDraft]:
    """Produce ordered segment drafts for all blocks across pages."""

    drafts: list[SegmentDraft] = []
    seq = 0
    for page in sorted(doc.pages, key=lambda p: p.page_index):
        for block in sorted(page.blocks, key=lambda b: b.reading_order):
            block_drafts = _drafts_for_block(block, seq_start=seq, max_chars=max_chars)
            drafts.extend(block_drafts)
            seq += len(block_drafts)
    return drafts
