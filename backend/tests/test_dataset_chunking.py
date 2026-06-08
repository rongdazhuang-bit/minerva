"""Unit tests for dataset chunk preview helpers."""

from __future__ import annotations

from app.dataset.rag.clean import clean_text
from app.dataset.rag.split import split_text
from app.dataset.service.chunk_service import parse_segmentation


def test_parse_segmentation_defaults() -> None:
    """Default segmentation values match process rule template."""

    delimiter, max_length, overlap = parse_segmentation(None)
    assert max_length == 1024
    assert overlap == 50


def test_split_text_by_paragraph_delimiter() -> None:
    """Splitting with a small max length yields multiple segments."""

    text = clean_text("paragraph one\n\nparagraph two\n\nparagraph three", None)
    chunks = split_text(text, delimiter="\n\n", max_length=20, overlap=0)
    assert len(chunks) >= 2
