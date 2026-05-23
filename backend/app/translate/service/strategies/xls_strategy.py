"""Excel legacy ``.xls`` document translation strategy."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import ClassVar

import xlrd
import xlwt

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy


class XlsTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.xls`` with one segment per non-empty sheet cell."""

    extensions: ClassVar[frozenset[str]] = frozenset({"xls"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
        layout_document=None,
    ) -> list[SegmentDraft]:
        """Extract one draft per non-empty cell using legacy XLS coordinates."""
        book = xlrd.open_workbook(str(local_path))
        drafts: list[SegmentDraft] = []
        seq = 0
        for sheet_idx in range(book.nsheets):
            sheet = book.sheet_by_index(sheet_idx)
            sheet_name = sheet.name
            for row_idx in range(sheet.nrows):
                for col_idx in range(sheet.ncols):
                    value = str(sheet.cell_value(row_idx, col_idx))
                    if not value.strip():
                        continue
                    drafts.append(
                        SegmentDraft(
                            seq=seq,
                            source_text=value,
                            anchor_json={
                                "sheet": sheet_name,
                                "sheet_index": sheet_idx,
                                "row": row_idx,
                                "col": col_idx,
                                "label": "table_cell",
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
        """Write translated XLS cells back while preserving untouched cells."""
        rb = xlrd.open_workbook(str(source_path))
        overrides: dict[tuple[int, int, int], str] = {}
        for seg in segments:
            anchor = seg.anchor_json or {}
            key = (
                int(anchor.get("sheet_index", 0)),
                int(anchor.get("row", 0)),
                int(anchor.get("col", 0)),
            )
            overrides[key] = (
                seg.source_text
                if anchor.get("skip_translate")
                else seg.translated_text or seg.source_text
            )

        wb = xlwt.Workbook()
        for sheet_idx in range(rb.nsheets):
            rs = rb.sheet_by_index(sheet_idx)
            ws = wb.add_sheet(rs.name)
            for row_idx in range(rs.nrows):
                for col_idx in range(rs.ncols):
                    value = overrides.get(
                        (sheet_idx, row_idx, col_idx),
                        rs.cell_value(row_idx, col_idx),
                    )
                    ws.write(row_idx, col_idx, value)
        wb.save(str(out_path))
