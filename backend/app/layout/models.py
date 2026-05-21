"""Pydantic models for layout-preserving OCR and document translation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LayoutBlock(BaseModel):
    """One translatable or structural region with optional page geometry."""

    block_key: str
    parent_key: str | None = None
    label: str
    reading_order: int
    source_text: str
    translated_text: str | None = None
    bbox: list[float] | None = None
    page_index: int | None = None
    sheet_name: str | None = None
    table_grid: dict[str, int] | None = None
    style_hint: dict[str, object] | None = None
    overflow_policy: Literal["shrink", "expand", "skip"] = "shrink"
    skip_translate: bool = False


class LayoutPage(BaseModel):
    """All blocks on one page or sheet."""

    page_index: int
    width: int | None = None
    height: int | None = None
    blocks: list[LayoutBlock] = Field(default_factory=list)


class LayoutDocument(BaseModel):
    """Full-document layout snapshot shared by OCR and translate pipelines."""

    pages: list[LayoutPage] = Field(default_factory=list)
    layout_source: Literal["native", "ocr", "hybrid"] = "native"
