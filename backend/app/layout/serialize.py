"""Serialize and deserialize layout pages for JSONB persistence."""

from __future__ import annotations

from typing import Any

from app.layout.models import LayoutBlock, LayoutDocument, LayoutPage


def layout_page_to_blocks_json(page: LayoutPage) -> list[dict[str, Any]]:
    """Dump page blocks for ``layout_blocks_json`` column storage."""

    return [block.model_dump(mode="json") for block in page.blocks]


def layout_page_from_blocks_json(
    *,
    page_index: int,
    width: int | None,
    height: int | None,
    blocks_json: list[dict[str, Any]] | None,
) -> LayoutPage:
    """Rebuild a ``LayoutPage`` from persisted JSONB."""

    blocks: list[LayoutBlock] = []
    if blocks_json:
        for raw in blocks_json:
            if isinstance(raw, dict):
                blocks.append(LayoutBlock.model_validate(raw))
    return LayoutPage(page_index=page_index, width=width, height=height, blocks=blocks)


def layout_document_from_paddle_pages(pages: list[LayoutPage]) -> LayoutDocument:
    """Wrap OCR pages as a layout document marked ``ocr`` source."""

    return LayoutDocument(pages=pages, layout_source="ocr")
