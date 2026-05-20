"""Abstract strategy for extracting and assembling one document format."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from app.translate.domain.dto import SegmentDraft, SegmentRecord


class DocTranslateFormatStrategy(ABC):
    """Maps one file extension to extract/assemble operations preserving layout."""

    extensions: ClassVar[frozenset[str]]

    def needs_ocr(self, local_path: Path) -> bool:
        """Return True when OCR must run before extract (PDF scans override)."""

        return False

    @abstractmethod
    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
    ) -> list[SegmentDraft]:
        """Split the document into ordered translatable paragraphs."""

    @abstractmethod
    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        """Write translated content back into a new file at ``out_path``."""
