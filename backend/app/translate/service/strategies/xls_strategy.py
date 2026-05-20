"""Excel legacy ``.xls`` document translation strategy."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import ClassVar

import xlrd
import xlwt

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy
from app.translate.service.strategies.xlsx_strategy import csv_split_tab


class XlsTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.xls`` with one segment per non-empty sheet row."""

    extensions: ClassVar[frozenset[str]] = frozenset({"xls"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
    ) -> list[SegmentDraft]:
        book = xlrd.open_workbook(str(local_path))
        drafts: list[SegmentDraft] = []
        seq = 0
        for sheet_idx in range(book.nsheets):
            sheet = book.sheet_by_index(sheet_idx)
            sheet_name = sheet.name
            for row_idx in range(sheet.nrows):
                cells = [str(sheet.cell_value(row_idx, col_idx)) for col_idx in range(sheet.ncols)]
                if not any(c.strip() for c in cells):
                    continue
                text = "\t".join(cells)
                drafts.append(
                    SegmentDraft(
                        seq=seq,
                        source_text=text,
                        anchor_json={
                            "sheet": sheet_name,
                            "sheet_index": sheet_idx,
                            "row": row_idx,
                            "cells": cells,
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
        rb = xlrd.open_workbook(str(source_path))
        overrides: dict[tuple[int, int], list[str]] = {}
        for seg in segments:
            anchor = seg.anchor_json or {}
            key = (int(anchor.get("sheet_index", 0)), int(anchor.get("row", 0)))
            overrides[key] = csv_split_tab(seg.translated_text)

        wb = xlwt.Workbook()
        for sheet_idx in range(rb.nsheets):
            rs = rb.sheet_by_index(sheet_idx)
            ws = wb.add_sheet(rs.name)
            for row_idx in range(rs.nrows):
                row_override = overrides.get((sheet_idx, row_idx))
                for col_idx in range(rs.ncols):
                    if row_override is not None and col_idx < len(row_override):
                        ws.write(row_idx, col_idx, row_override[col_idx])
                    else:
                        ws.write(row_idx, col_idx, rs.cell_value(row_idx, col_idx))
        wb.save(str(out_path))
