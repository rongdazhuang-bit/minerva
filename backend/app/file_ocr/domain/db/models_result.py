"""ORM models for per-engine OCR output tables tied to ``ocr_file``."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class OcrFilePaddleocr(Base):
    """Stores PaddleOCR-VL layout output keyed by source ``ocr_file`` row."""

    __tablename__ = "ocr_file_paddleocr"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    markdown_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_images: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OcrFileMineru(Base):
    """Reserved MinerU output table; populated when the MinerU strategy is enabled."""

    __tablename__ = "ocr_file_mineru"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    markdown_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_images: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
