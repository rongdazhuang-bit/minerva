"""CSV document translation strategy (one row per segment)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import ClassVar

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy


class CsvTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.csv`` with one segment per data row."""

    extensions: ClassVar[frozenset[str]] = frozenset({"csv"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
    ) -> list[SegmentDraft]:
        text = local_path.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()
        if not lines:
            return []
        drafts: list[SegmentDraft] = []
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            drafts.append(
                SegmentDraft(seq=i, source_text=line, anchor_json={"row": i, "raw_line": line})
            )
        return drafts

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        by_row = {
            int(s.anchor_json["row"]) if s.anchor_json else s.seq: s.translated_text
            for s in segments
        }
        lines = source_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        for row_idx, translated in by_row.items():
            if 0 <= row_idx < len(lines):
                lines[row_idx] = translated
        out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8-sig")
