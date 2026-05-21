"""Unit tests for layout page → Markdown rendering."""

from app.layout.models import LayoutBlock, LayoutPage
from app.layout.to_markdown import page_markdown


def test_formula_unchanged_in_markdown() -> None:
    """Formula source text is emitted verbatim for KaTeX rendering."""
    page = LayoutPage(
        page_index=0,
        blocks=[
            LayoutBlock(
                block_key="p0.b1",
                label="formula",
                reading_order=1,
                source_text="$E=mc^2$",
                skip_translate=True,
                overflow_policy="skip",
            )
        ],
    )
    md = page_markdown(page, use_translation=False)
    assert "$E=mc^2$" in md


def test_translated_markdown_keeps_formula() -> None:
    """Skip-translate blocks use source text even when use_translation is true."""
    page = LayoutPage(
        page_index=0,
        blocks=[
            LayoutBlock(
                block_key="p0.b1",
                label="formula",
                reading_order=1,
                source_text="$E=mc^2$",
                translated_text="should-not-appear",
                skip_translate=True,
                overflow_policy="skip",
            )
        ],
    )
    md = page_markdown(page, use_translation=True)
    assert "$E=mc^2$" in md
    assert "should-not-appear" not in md
