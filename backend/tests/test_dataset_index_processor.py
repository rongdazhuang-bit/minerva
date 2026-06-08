"""Unit tests for index processors (text, hierarchical, Q&A)."""

from __future__ import annotations

from app.dataset.domain.constants import DOC_FORM_HIERARCHICAL, DOC_FORM_QA, DOC_FORM_TEXT
from app.dataset.rag.index_processor import (
    build_hierarchical_units,
    build_index_units,
    build_qa_units,
    split_children_for_parent,
)


def test_build_text_units_splits_paragraphs() -> None:
    """Plain text mode yields one unit per split chunk."""

    units = build_index_units(
        "alpha\n\nbeta\n\ngamma",
        doc_form=DOC_FORM_TEXT,
        process_rule={"rules": {"segmentation": {"delimiter": "\\n\\n", "max_length": 8, "chunk_overlap": 0}}},
    )
    assert len(units) >= 2
    assert all(not unit.children for unit in units)


def test_build_hierarchical_units_create_children() -> None:
    """Parent-child mode stores child chunks under each parent unit."""

    parent_text = "sentence one. sentence two. sentence three. sentence four."
    units = build_hierarchical_units(
        parent_text,
        process_rule={
            "rules": {
                "parent_mode": {"delimiter": ".", "max_length": 200, "chunk_overlap": 0},
                "subchunk_segmentation": {"delimiter": " ", "max_length": 12, "chunk_overlap": 0},
            }
        },
    )
    assert len(units) >= 1
    assert units[0].children
    assert all(child.strip() for child in units[0].children)


def test_build_qa_units_parses_blocks() -> None:
    """Q&A mode extracts question and answer pairs."""

    text = "Q: What is Minerva?\nA: A knowledge platform.\n\nQ: Who uses it?\nA: Teams."
    units = build_qa_units(text, process_rule=None)
    assert len(units) == 2
    assert units[0].content == "What is Minerva?"
    assert units[0].answer == "A knowledge platform."


def test_build_qa_units_fallback_to_text() -> None:
    """Without Q/A markers, qa mode falls back to plain splitting."""

    units = build_index_units(
        "plain paragraph without markers",
        doc_form=DOC_FORM_QA,
        process_rule=None,
    )
    assert len(units) >= 1
    assert units[0].answer is None


def test_hierarchical_full_doc_uses_single_parent() -> None:
    """Full-doc parent mode keeps the entire body as one parent chunk."""

    text = "section one\n\nsection two\n\nsection three"
    units = build_hierarchical_units(
        text,
        process_rule={
            "rules": {
                "parent_mode_type": "full-doc",
                "subchunk_segmentation": {"delimiter": " ", "max_length": 12, "chunk_overlap": 0},
            }
        },
    )
    assert len(units) == 1
    assert units[0].content == text
    assert units[0].children


def test_hierarchical_dispatch() -> None:
    """build_index_units routes hierarchical doc_form correctly."""

    units = build_index_units(
        "part one\n\npart two",
        doc_form=DOC_FORM_HIERARCHICAL,
        process_rule={
            "rules": {
                "parent_mode": {"delimiter": "\\n\\n", "max_length": 100, "chunk_overlap": 0},
                "subchunk_segmentation": {"delimiter": " ", "max_length": 10, "chunk_overlap": 0},
            }
        },
    )
    assert units
    assert units[0].children


def test_split_children_for_parent_fallback_to_whole_body() -> None:
    """Short parent text still yields at least one child chunk."""

    children = split_children_for_parent(
        "short",
        process_rule={"rules": {"subchunk_segmentation": {"delimiter": " ", "max_length": 100, "chunk_overlap": 0}}},
    )
    assert children == ["short"]
