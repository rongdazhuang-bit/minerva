"""Tests for text capacity estimation."""

from __future__ import annotations

from app.agent.skills.ppt.shared.capacity import check_text_overflow, estimate_text_capacity


def test_estimate_capacity_scales_with_width() -> None:
    """Wider placeholders allow more visual character units."""

    cap = estimate_text_capacity(width_pt=400.0, font_size_pt=18.0, lines=1)
    assert cap > estimate_text_capacity(width_pt=200.0, font_size_pt=18.0, lines=1)


def test_check_overflow_returns_warning() -> None:
    """Long CJK text against a narrow box yields overflow warnings."""

    warnings = check_text_overflow(
        text="这是一段很长的标题" * 20,
        width_pt=100.0,
        font_size_pt=24.0,
        label="title",
    )
    assert warnings
