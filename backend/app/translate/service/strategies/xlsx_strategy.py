"""Excel xlsx document translation strategy."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, ClassVar

from openpyxl import load_workbook

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy


class XlsxTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.xlsx`` with one segment per non-empty sheet row."""

    extensions: ClassVar[frozenset[str]] = frozenset({"xlsx"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
        layout_document=None,
    ) -> list[SegmentDraft]:
        wb = load_workbook(local_path, read_only=True, data_only=True)
        drafts: list[SegmentDraft] = []
        seq = 0
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                cells = [str(c) if c is not None else "" for c in row]
                if not any(c.strip() for c in cells):
                    continue
                text = "\t".join(cells)
                drafts.append(
                    SegmentDraft(
                        seq=seq,
                        source_text=text,
                        anchor_json={
                            "sheet": sheet_name,
                            "row": row_idx,
                            "cells": cells,
                        },
                    )
                )
                seq += 1
        wb.close()
        return drafts

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        wb = load_workbook(source_path)
        for seg in segments:
            anchor = seg.anchor_json or {}
            sheet_name = str(anchor.get("sheet", wb.sheetnames[0]))
            row_idx = int(anchor.get("row", 1))
            cells = list(csv_split_tab(seg.translated_text))
            ws = wb[sheet_name]
            for col_idx, value in enumerate(cells, start=1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        wb.save(out_path)
        wb.close()


def csv_split_tab(line: str) -> list[str]:
    """Split a tab-joined row produced during extract."""

    return line.split("\t")
