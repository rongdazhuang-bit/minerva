"""Plain text document translation strategy."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import ClassVar

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy
from app.translate.service.text_segmentation import split_plain_text_into_segments


class TxtTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.txt`` files by blank-line paragraphs."""

    extensions: ClassVar[frozenset[str]] = frozenset({"txt"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
        layout_document=None,
    ) -> list[SegmentDraft]:
        text = local_path.read_text(encoding="utf-8", errors="replace")
        paragraphs = split_plain_text_into_segments(text)
        return [
            SegmentDraft(seq=i, source_text=p, anchor_json={"paragraph": i})
            for i, p in enumerate(paragraphs)
            if p.strip()
        ]

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        ordered = sorted(segments, key=lambda s: s.seq)
        out_path.write_text(
            "\n\n".join(s.translated_text for s in ordered),
            encoding="utf-8",
        )
