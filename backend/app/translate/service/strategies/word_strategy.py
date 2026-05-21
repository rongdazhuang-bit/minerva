"""Word ``.docx`` and legacy ``.doc`` translation (``.doc`` via LibreOffice → docx)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import ClassVar

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.office_convert import convert_office_file
from app.translate.service.strategies.base import DocTranslateFormatStrategy
from app.translate.service.strategies.docx_strategy import DocxTranslateStrategy


class WordTranslateStrategy(DocTranslateFormatStrategy):
    """Translate Word documents; ``.doc`` is converted to docx for extract/assemble."""

    extensions: ClassVar[frozenset[str]] = frozenset({"docx", "doc"})

    def __init__(self) -> None:
        self._docx = DocxTranslateStrategy()

    def _docx_work_path(self, local_path: Path) -> Path:
        """Return a ``.docx`` path suitable for python-docx (convert ``.doc`` when needed)."""

        if local_path.suffix.lower() == ".docx":
            return local_path
        return convert_office_file(
            local_path,
            out_dir=local_path.parent,
            target_ext="docx",
        )

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
        layout_document=None,
    ) -> list[SegmentDraft]:
        docx_path = self._docx_work_path(local_path)
        return self._docx.extract(
            docx_path,
            ocr_file_id=ocr_file_id,
            ocr_pages=ocr_pages,
            layout_document=layout_document,
        )

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        if source_path.suffix.lower() == ".doc":
            docx_src = self._docx_work_path(source_path)
            docx_out = source_path.parent / f"{source_path.stem}__tr.docx"
            self._docx.assemble(segments, docx_src, docx_out)
            produced = convert_office_file(
                docx_out,
                out_dir=source_path.parent,
                target_ext="doc",
            )
            if produced.resolve() != out_path.resolve():
                shutil.move(str(produced), str(out_path))
            if docx_out.is_file():
                docx_out.unlink(missing_ok=True)
            return
        self._docx.assemble(segments, source_path, out_path)
