"""Fit translated text into layout boxes (shrink / expand policies)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OverflowPolicy = Literal["shrink", "expand", "skip"]


@dataclass(frozen=True)
class OverflowResult:
    """Outcome of fitting text into a target box."""

    text: str
    font_size_pt: float
    truncated: bool
    warning: str | None = None
    expanded_height: float | None = None


def _estimate_chars_per_line(*, width: float, font_size_pt: float) -> int:
    """Heuristic character capacity per line for Latin/CJK mixed text."""

    return max(4, int(width / max(font_size_pt * 0.55, 4.0)))


def fit_text_to_box(
    text: str,
    *,
    width: float,
    height: float,
    policy: OverflowPolicy,
    base_font_pt: float = 12.0,
    min_font_pt: float = 6.0,
) -> OverflowResult:
    """
    Choose font size and optional truncation for one text box.

    shrink: decrease font until estimated lines fit height, else truncate.
    expand: keep base font; report expanded_height when content needs more lines.
    skip: return text unchanged at base font.
    """

    content = text or ""
    if policy == "skip":
        return OverflowResult(text=content, font_size_pt=base_font_pt, truncated=False)

    chars_per_line = _estimate_chars_per_line(width=width, font_size_pt=base_font_pt)
    line_count = max(1, (len(content) + chars_per_line - 1) // chars_per_line)
    line_height = base_font_pt * 1.25
    needed_height = line_count * line_height

    if policy == "expand":
        expanded = max(height, needed_height)
        return OverflowResult(
            text=content,
            font_size_pt=base_font_pt,
            truncated=False,
            expanded_height=expanded,
        )

    font = base_font_pt
    while font > min_font_pt:
        chars_per_line = _estimate_chars_per_line(width=width, font_size_pt=font)
        line_count = max(1, (len(content) + chars_per_line - 1) // chars_per_line)
        if line_count * font * 1.25 <= height:
            return OverflowResult(text=content, font_size_pt=font, truncated=False)
        font -= 0.5

    chars_per_line = _estimate_chars_per_line(width=width, font_size_pt=min_font_pt)
    max_lines = max(1, int(height / (min_font_pt * 1.25)))
    max_chars = chars_per_line * max_lines
    if len(content) <= max_chars:
        return OverflowResult(text=content, font_size_pt=min_font_pt, truncated=False)
    trimmed = content[: max(0, max_chars - 1)].rstrip() + "…"
    return OverflowResult(
        text=trimmed,
        font_size_pt=min_font_pt,
        truncated=True,
        warning="translate.layout_text_truncated",
    )
