"""Word docx document translation strategy."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import ClassVar

from docx import Document

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy


class DocxTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.docx`` paragraphs and table cells preserving structure."""

    extensions: ClassVar[frozenset[str]] = frozenset({"docx"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
    ) -> list[SegmentDraft]:
        doc = Document(local_path)
        drafts: list[SegmentDraft] = []
        seq = 0
        for p_idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if not text:
                continue
            drafts.append(
                SegmentDraft(
                    seq=seq,
                    source_text=text,
                    anchor_json={"kind": "paragraph", "index": p_idx},
                )
            )
            seq += 1
        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    text = cell.text.strip()
                    if not text:
                        continue
                    drafts.append(
                        SegmentDraft(
                            seq=seq,
                            source_text=text,
                            anchor_json={
                                "kind": "table_cell",
                                "table": t_idx,
                                "row": r_idx,
                                "col": c_idx,
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
        doc = Document(source_path)
        for seg in segments:
            anchor = seg.anchor_json or {}
            kind = anchor.get("kind")
            if kind == "paragraph":
                idx = int(anchor.get("index", 0))
                if idx < len(doc.paragraphs):
                    doc.paragraphs[idx].text = seg.translated_text
            elif kind == "table_cell":
                t_idx = int(anchor.get("table", 0))
                r_idx = int(anchor.get("row", 0))
                c_idx = int(anchor.get("col", 0))
                if t_idx < len(doc.tables):
                    table = doc.tables[t_idx]
                    if r_idx < len(table.rows) and c_idx < len(table.rows[r_idx].cells):
                        table.rows[r_idx].cells[c_idx].text = seg.translated_text
        doc.save(out_path)
