"""Persisted document translation jobs and per-paragraph segments (no DB foreign keys)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Index, Integer, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class DocTranslateJob(Base):
    """One uploaded file translation task; appears as one row in the UI history sidebar."""

    __tablename__ = "doc_translate_job"
    __table_args__ = (
        Index("ix_doc_translate_job_workspace_updated", "workspace_id", "update_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_ext: Mapped[str] = mapped_column(String(16), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(32), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    result_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ocr_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=True,
    )
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=sa.text("0"))
    segment_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    segment_done: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    layout_snapshot_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    layout_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocTranslateSegment(Base):
    """One translatable paragraph unit within a job (source/target text and strategy anchor)."""

    __tablename__ = "doc_translate_segment"
    __table_args__ = (Index("ix_doc_translate_segment_job_seq", "job_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    anchor_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
