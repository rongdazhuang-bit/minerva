"""MinerU result read strategy: ``ocr_file_mineru``."""

from __future__ import annotations

import uuid
from typing import ClassVar

from sqlalchemy import asc, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models_result import OcrFileMineru

from .base import FileOcrResultReadStrategy, RawOcrResultPage


class MineruOcrResultReadStrategy(FileOcrResultReadStrategy):
    """Reads per-page markdown from ``ocr_file_mineru``."""

    ocr_type: ClassVar[str] = "MINERU"

    async def load_pages(
        self,
        *,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> list[RawOcrResultPage]:
        """Select all pages for ``file_id`` in the workspace, ordered by page index."""

        stmt = (
            select(OcrFileMineru)
            .where(
                OcrFileMineru.workspace_id == workspace_id,
                OcrFileMineru.file_id == file_id,
            )
            .order_by(nullslast(asc(OcrFileMineru.page_index)), asc(OcrFileMineru.id))
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [
            RawOcrResultPage(
                page_index=r.page_index,
                markdown_text=r.markdown_text,
                markdown_images=r.markdown_images,
            )
            for r in rows
        ]

