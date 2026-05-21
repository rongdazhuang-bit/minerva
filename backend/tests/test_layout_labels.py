"""Unit tests for layout block label normalization."""

from app.layout.labels import normalize_block_label


def test_formula_labels_skip_translate() -> None:
    """Formula-like Paddle labels must not be machine-translated."""
    meta = normalize_block_label("inline_formula")
    assert meta.label == "formula"
    assert meta.skip_translate is True
    assert meta.overflow_policy == "skip"


def test_text_label_shrink() -> None:
    """Body text uses shrink overflow policy."""
    meta = normalize_block_label("text")
    assert meta.label == "text"
    assert meta.skip_translate is False
    assert meta.overflow_policy == "shrink"


def test_title_label_expand() -> None:
    """Titles may expand their box when translated text is longer."""
    meta = normalize_block_label("doc_title")
    assert meta.label == "title"
    assert meta.overflow_policy == "expand"
