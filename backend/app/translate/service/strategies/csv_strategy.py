"""CSV document translation strategy with field-level anchors."""

from __future__ import annotations

import csv
import uuid
from io import StringIO
from pathlib import Path
from typing import ClassVar

from app.layout.writers.base import WriteContext
from app.layout.writers.text_writer import CsvFieldWriter
from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy


class CsvTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.csv`` by extracting non-header data fields."""

    extensions: ClassVar[frozenset[str]] = frozenset({"csv"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
        layout_document=None,
    ) -> list[SegmentDraft]:
        """Extract one draft per non-empty data cell, excluding the header row."""
        text = local_path.read_text(encoding="utf-8-sig", errors="replace")
        rows = list(csv.reader(StringIO(text)))
        drafts: list[SegmentDraft] = []
        seq = 0
        for row_idx, row in enumerate(rows):
            if row_idx == 0:
                continue
            for field_idx, field in enumerate(row):
                if not field.strip():
                    continue
                drafts.append(
                    SegmentDraft(
                        seq=seq,
                        source_text=field,
                        anchor_json={
                            "row": row_idx,
                            "field_index": field_idx,
                            "label": "csv_field",
                        },
                    )
                )
                seq += 1
        return drafts

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        """Write translated CSV fields back to their original cell positions."""
        CsvFieldWriter().write(
            WriteContext(
                source_path=source_path,
                out_path=out_path,
                segments=segments,
            )
        )
