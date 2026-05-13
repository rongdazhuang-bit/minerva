"""MinerU strategy placeholder until MINERU is added to the INIT scan allowlist."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models import OcrFile
from app.sys.tool.ocr.domain.db.models import SysOcrTool

from .base import FileOcrEngineStrategy


class MineruFileStrategy(FileOcrEngineStrategy):
    """Reserved MinerU adapter; scanning MINERU tasks stays disabled in the first release."""

    ocr_type: ClassVar[str] = "MINERU"

    async def process(
        self,
        *,
        session: AsyncSession,
        ocr_file: OcrFile,
        tool: SysOcrTool,
    ) -> None:
        """Explicitly fail fast if this path is wired before the MinerU HTTP flow exists."""

        del session, ocr_file, tool
        raise NotImplementedError("MinerU file OCR processing is not enabled in this release.")
