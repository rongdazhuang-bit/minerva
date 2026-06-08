"""Index processors for text, parent-child, and Q&A chunk structures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.dataset.domain.constants import (
    DOC_FORM_HIERARCHICAL,
    DOC_FORM_QA,
    DOC_FORM_TEXT,
)
from app.dataset.rag.segmentation_rules import (
    parse_parent_mode_type,
    parse_parent_segmentation,
    parse_segmentation,
    parse_subchunk_segmentation,
)
from app.dataset.rag.split import split_text


@dataclass
class IndexSegmentUnit:
    """One logical segment produced before persistence and vector indexing."""

    content: str
    answer: str | None = None
    children: list[str] = field(default_factory=list)


def build_text_units(text: str, *, process_rule: dict | None) -> list[IndexSegmentUnit]:
    """Split plain text into segment units."""

    delimiter, max_length, overlap = parse_segmentation(process_rule)
    segments = split_text(text, delimiter=delimiter, max_length=max_length, overlap=overlap)
    return [IndexSegmentUnit(content=segment) for segment in segments if segment.strip()]


def build_hierarchical_units(text: str, *, process_rule: dict | None) -> list[IndexSegmentUnit]:
    """Split text into parent segments each with retrieval child chunks."""

    parent_mode_type = parse_parent_mode_type(process_rule)
    child_delim, child_max, child_overlap = parse_subchunk_segmentation(process_rule)
    if parent_mode_type == "full-doc":
        stripped = text.strip()
        parents = [stripped[:10000]] if stripped else []
    else:
        parent_delim, parent_max, parent_overlap = parse_parent_segmentation(process_rule)
        parents = split_text(
            text,
            delimiter=parent_delim,
            max_length=parent_max,
            overlap=parent_overlap,
        )
    units: list[IndexSegmentUnit] = []
    for parent in parents:
        parent = parent.strip()
        if not parent:
            continue
        children = split_text(
            parent,
            delimiter=child_delim,
            max_length=child_max,
            overlap=child_overlap,
        )
        child_texts = [child.strip() for child in children if child.strip()]
        if not child_texts:
            child_texts = [parent]
        units.append(IndexSegmentUnit(content=parent, children=child_texts))
    return units


def split_children_for_parent(parent_text: str, *, process_rule: dict | None) -> list[str]:
    """Split one parent segment body into child chunk texts for hierarchical mode."""

    parent = parent_text.strip()
    if not parent:
        return []
    child_delim, child_max, child_overlap = parse_subchunk_segmentation(process_rule)
    children = split_text(
        parent,
        delimiter=child_delim,
        max_length=child_max,
        overlap=child_overlap,
    )
    child_texts = [child.strip() for child in children if child.strip()]
    if not child_texts:
        child_texts = [parent]
    return child_texts


_QA_BLOCK_PATTERN = re.compile(
    r"(?:^|\n)(?:Q|问)[:：]\s*(?P<question>.+?)\n(?:A|答)[:：]\s*(?P<answer>.+?)(?=(?:\n(?:Q|问)[:：])|\Z)",
    re.DOTALL,
)


def build_qa_units(text: str, *, process_rule: dict | None) -> list[IndexSegmentUnit]:
    """Parse Q/A blocks; fall back to plain text when no markers are found."""

    stripped = text.strip()
    if not stripped:
        return []
    matches = list(_QA_BLOCK_PATTERN.finditer(stripped))
    if matches:
        units: list[IndexSegmentUnit] = []
        for match in matches:
            question = match.group("question").strip()
            answer = match.group("answer").strip()
            if question:
                units.append(IndexSegmentUnit(content=question, answer=answer or None))
        return units
    return build_text_units(stripped, process_rule=process_rule)


def build_index_units(
    text: str,
    *,
    doc_form: str,
    process_rule: dict | None,
) -> list[IndexSegmentUnit]:
    """Dispatch to the processor matching ``doc_form``."""

    form = (doc_form or DOC_FORM_TEXT).strip()
    if form == DOC_FORM_HIERARCHICAL:
        return build_hierarchical_units(text, process_rule=process_rule)
    if form == DOC_FORM_QA:
        return build_qa_units(text, process_rule=process_rule)
    return build_text_units(text, process_rule=process_rule)
