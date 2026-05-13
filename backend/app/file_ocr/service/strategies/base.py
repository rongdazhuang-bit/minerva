"""Abstract strategy for processing one ``ocr_file`` row with a configured OCR tool."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models import OcrFile
from app.sys.tool.ocr.domain.db.models import SysOcrTool


class FileOcrEngineStrategy(ABC):
    """Maps one ``ocr_type`` to vendor HTTP calls and result-table persistence."""

    ocr_type: ClassVar[str]

    @abstractmethod
    async def process(
        self,
        *,
        session: AsyncSession,
        ocr_file: OcrFile,
        tool: SysOcrTool,
    ) -> None:
        """Run OCR for ``ocr_file`` using ``tool`` and update ``ocr_file`` to a terminal state."""
