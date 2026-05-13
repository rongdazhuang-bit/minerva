"""Abstract read strategy and neutral page row for OCR markdown detail."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RawOcrResultPage:
    """One page row before JSON coercion (``markdown_images`` still raw DB text)."""

    page_index: int | None
    markdown_text: str | None
    markdown_images: str | None


class FileOcrResultReadStrategy(ABC):
    """Loads ordered result rows for a finished ``ocr_file`` from the engine-specific table."""

    ocr_type: ClassVar[str]

    @abstractmethod
    async def load_pages(
        self,
        *,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> list[RawOcrResultPage]:
        """Return pages ordered by ``page_index ASC NULLS LAST`` (SQL-side)."""

