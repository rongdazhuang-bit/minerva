"""Build ``LayoutPage`` rows from PaddleOCR-VL ``prunedResult`` payloads."""

from __future__ import annotations

from app.layout.labels import normalize_block_label
from app.layout.models import LayoutBlock, LayoutPage
from app.ocr.paddleocr.pruned_result import ParsingResBlock, PrunedResult


def _block_sort_key(item: ParsingResBlock) -> tuple[int, int, int]:
    """Order blocks by reading order, then block id."""

    order = item.block_order if item.block_order is not None else 1_000_000 + item.block_id
    return (0 if item.block_order is not None else 1, order, item.block_id)


def layout_page_from_pruned(page_index: int, pr: PrunedResult) -> LayoutPage:
    """Convert one page ``prunedResult`` into a ``LayoutPage`` with normalized blocks."""

    blocks: list[LayoutBlock] = []
    for item in sorted(pr.parsing_res_list, key=_block_sort_key):
        meta = normalize_block_label(item.block_label)
        content = item.block_content or ""
        if meta.label == "figure" and not content.strip():
            content = ""
        bbox = list(item.block_bbox) if len(item.block_bbox) >= 4 else None
        blocks.append(
            LayoutBlock(
                block_key=f"p{page_index}.b{item.block_id}",
                label=meta.label,
                reading_order=item.block_order if item.block_order is not None else item.block_id,
                source_text=content,
                bbox=bbox,
                page_index=page_index,
                overflow_policy=meta.overflow_policy,
                skip_translate=meta.skip_translate,
            )
        )
    return LayoutPage(page_index=page_index, width=pr.width, height=pr.height, blocks=blocks)
