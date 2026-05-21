"""Split plain text into translation segments (blank lines, numbered clauses, size cap)."""

from __future__ import annotations

import re

from app.translate.domain.constants import DOC_TRANSLATE_MAX_SEGMENT_CHARS

# Sub-clauses such as ``2.0.1`` alone or ``2.0.1 风电场``.
_SUBSECTION_ONLY_RE = re.compile(r"^\d+\.\d+(?:\.\d+)*\s*$")
_SUBSECTION_WITH_TEXT_RE = re.compile(r"^\d+\.\d+(?:\.\d+)*\s+\S")

# Top-level sections such as ``1 总则`` / ``3 风电场``.
_SECTION_LINE_RE = re.compile(r"^\d+\s+\S")


def _split_blank_line_paragraphs(text: str) -> list[str]:
    """Split on blank lines while preserving non-empty paragraph order."""

    parts: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if buf:
                parts.append("\n".join(buf))
                buf = []
        else:
            buf.append(line)
    if buf:
        parts.append("\n".join(buf))
    return parts if parts else ([text] if text.strip() else [])


def _is_numbered_clause_line(line: str) -> bool:
    """Return True when a line starts a numbered section or sub-clause."""

    stripped = line.strip()
    if not stripped:
        return False
    return bool(
        _SUBSECTION_ONLY_RE.match(stripped)
        or _SUBSECTION_WITH_TEXT_RE.match(stripped)
        or _SECTION_LINE_RE.match(stripped)
    )


def _split_numbered_clause_blocks(block: str) -> list[str]:
    """Further split one paragraph on numbered line starts (e.g. ``2.0.1``)."""

    lines = block.splitlines()
    if len(lines) <= 1:
        return [block] if block.strip() else []

    chunks: list[str] = []
    buf: list[str] = []
    for line in lines:
        if _is_numbered_clause_line(line) and buf:
            chunks.append("\n".join(buf))
            buf = [line]
        else:
            buf.append(line)
    if buf:
        chunks.append("\n".join(buf))
    return chunks if chunks else ([block] if block.strip() else [])


def _split_by_char_budget(text: str, max_chars: int) -> list[str]:
    """Split text so each part is at most ``max_chars`` (prefer line boundaries)."""

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines():
        line_len = len(line) + (1 if buf else 0)
        if size + line_len > max_chars and buf:
            chunks.append("\n".join(buf))
            buf = [line]
            size = len(line)
        else:
            buf.append(line)
            size += line_len
    if buf:
        chunks.append("\n".join(buf))

    out: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            out.append(chunk)
            continue
        for offset in range(0, len(chunk), max_chars):
            piece = chunk[offset : offset + max_chars]
            if piece.strip():
                out.append(piece)
    return out


def split_plain_text_into_segments(
    text: str,
    *,
    max_chars: int = DOC_TRANSLATE_MAX_SEGMENT_CHARS,
) -> list[str]:
    """Produce ordered segments: blank-line blocks, then numbered clauses, then size chunks."""

    segments: list[str] = []
    for paragraph in _split_blank_line_paragraphs(text):
        for clause in _split_numbered_clause_blocks(paragraph):
            segments.extend(_split_by_char_budget(clause, max_chars))
    return [s for s in segments if s.strip()]
