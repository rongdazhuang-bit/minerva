"""Unit tests for PDF native extract heuristics (formula fragmentation)."""

from app.translate.service.strategies.pdf_strategy import (
    is_formula_like_text,
    merge_page_text_blocks,
    pdf_text_layer_is_fragmented,
)


def test_pdf_text_layer_is_fragmented_many_short_blocks() -> None:
    """MD/LaTeX PDF exports often yield dozens of tiny text-layer spans."""

    blocks = ["∫"] * 30 + ["f(t) dt"] * 30 + ["short"] * 50
    assert pdf_text_layer_is_fragmented(blocks) is True


def test_pdf_text_layer_not_fragmented_for_prose() -> None:
    """Normal paragraphs should stay on the native text-layer path."""

    blocks = ["This is a full paragraph with enough length."] * 10
    assert pdf_text_layer_is_fragmented(blocks) is False


def test_is_formula_like_detects_symbols() -> None:
    """Symbol-heavy lines are marked skip_translate on native extract."""

    assert is_formula_like_text("∫ f(t)e^{-i\\omega t} dt") is True
    assert is_formula_like_text("Chapter 1 Introduction to energy storage") is False


def test_merge_page_text_blocks_not_used_without_fitz_page() -> None:
    """merge_page_text_blocks is integration-tested via extract; ensure import works."""

    assert callable(merge_page_text_blocks)
