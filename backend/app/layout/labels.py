"""Map vendor block labels to normalized layout metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OverflowPolicy = Literal["shrink", "expand", "skip"]

FORMULA_RAW_LABELS = frozenset(
    {
        "formula",
        "equation",
        "inline_formula",
        "interline_equation",
        "display_formula",
        "math",
    }
)

FIGURE_RAW_LABELS = frozenset(
    {
        "figure",
        "image",
        "chart",
        "seal",
        "header_image",
        "footer_image",
        "picture",
    }
)

TITLE_RAW_LABELS = frozenset(
    {
        "title",
        "doc_title",
        "paragraph_title",
        "section_title",
        "heading",
    }
)

FOOTNOTE_RAW_LABELS = frozenset(
    {
        "footnote",
        "footer",
        "caption",
        "reference",
    }
)

TABLE_RAW_LABELS = frozenset({"table"})


@dataclass(frozen=True)
class BlockLabelMeta:
    """Normalized label and policies for one raw vendor label."""

    label: str
    overflow_policy: OverflowPolicy
    skip_translate: bool


def normalize_block_label(raw_label: str) -> BlockLabelMeta:
    """Classify a Paddle or detector label into LDM policy fields."""

    key = (raw_label or "").strip().lower()
    if key in FORMULA_RAW_LABELS:
        return BlockLabelMeta(label="formula", overflow_policy="skip", skip_translate=True)
    if key in FIGURE_RAW_LABELS:
        return BlockLabelMeta(label="figure", overflow_policy="skip", skip_translate=True)
    if key in TABLE_RAW_LABELS:
        return BlockLabelMeta(label="table", overflow_policy="expand", skip_translate=False)
    if key in TITLE_RAW_LABELS:
        return BlockLabelMeta(label="title", overflow_policy="expand", skip_translate=False)
    if key in FOOTNOTE_RAW_LABELS:
        return BlockLabelMeta(label="footnote", overflow_policy="shrink", skip_translate=False)
    return BlockLabelMeta(label="text", overflow_policy="shrink", skip_translate=False)
