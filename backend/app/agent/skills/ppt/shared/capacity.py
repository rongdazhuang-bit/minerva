"""Visual text capacity estimation for layout_fill warnings."""

from __future__ import annotations

# CJK ≈ 1.0 unit width; Latin ≈ 0.55 at same font size
_CJK_RATIO = 1.0
_LATIN_RATIO = 0.55


def _visual_length(text: str) -> float:
    """Return weighted visual length treating CJK wider than Latin."""

    total = 0.0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            total += _CJK_RATIO
        else:
            total += _LATIN_RATIO
    return total


def estimate_text_capacity(*, width_pt: float, font_size_pt: float, lines: int = 1) -> float:
    """Estimate safe visual character units for a text box."""

    chars_per_line = max(width_pt / max(font_size_pt * 0.6, 1.0), 1.0)
    return chars_per_line * max(lines, 1)


def check_text_overflow(
    *,
    text: str,
    width_pt: float,
    font_size_pt: float,
    label: str,
    lines: int = 1,
) -> list[str]:
    """Return warning strings when text likely overflows its placeholder."""

    if not text.strip():
        return []
    capacity = estimate_text_capacity(width_pt=width_pt, font_size_pt=font_size_pt, lines=lines)
    if _visual_length(text) > capacity * 1.05:
        return [
            f"text may overflow placeholder '{label}' ({len(text)} chars vs ~{int(capacity)} capacity)"
        ]
    return []
