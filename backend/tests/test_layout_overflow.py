"""Unit tests for layout text overflow fitting."""

from app.layout.overflow import fit_text_to_box


def test_shrink_reduces_font_until_fits() -> None:
    """Short text keeps or lowers font size within the box."""
    result = fit_text_to_box(
        "hello world",
        width=120.0,
        height=40.0,
        policy="shrink",
        base_font_pt=12.0,
    )
    assert result.font_size_pt <= 12.0
    assert result.truncated is False


def test_shrink_truncates_when_min_font_exceeded() -> None:
    """Very long text truncates with a warning at minimum font."""
    long_text = "x" * 500
    result = fit_text_to_box(
        long_text,
        width=30.0,
        height=10.0,
        policy="shrink",
        base_font_pt=6.0,
        min_font_pt=6.0,
    )
    assert result.truncated is True
    assert result.warning == "translate.layout_text_truncated"
