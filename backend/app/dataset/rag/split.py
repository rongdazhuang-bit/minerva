"""Character-based text splitting aligned with Dify fixed delimiter mode."""

from __future__ import annotations


def _merge_with_overlap(chunks: list[str], overlap: int) -> list[str]:
    """Apply chunk overlap by prefixing tail of previous chunk."""

    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    merged: list[str] = [chunks[0]]
    for chunk in chunks[1:]:
        prev = merged[-1]
        prefix = prev[-overlap:] if len(prev) > overlap else prev
        merged.append((prefix + chunk).strip())
    return merged


def split_text(
    text: str,
    *,
    delimiter: str,
    max_length: int,
    overlap: int = 0,
) -> list[str]:
    """Split cleaned text into segments under ``max_length`` characters."""

    if not text:
        return []
    raw_delim = delimiter.encode().decode("unicode_escape") if delimiter.startswith("\\") else delimiter
    parts = text.split(raw_delim) if raw_delim else [text]
    chunks: list[str] = []
    buffer = ""
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        candidate = f"{buffer}{raw_delim}{piece}".strip() if buffer else piece
        if len(candidate) <= max_length:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
        if len(piece) <= max_length:
            buffer = piece
            continue
        start = 0
        while start < len(piece):
            chunks.append(piece[start : start + max_length])
            start += max(max_length - overlap, 1)
        buffer = ""
    if buffer:
        chunks.append(buffer)
    return _merge_with_overlap(chunks, overlap)
