"""Request/response schemas for file OCR APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OcrFileOverviewStatsOut(BaseModel):
    """Grouped OCR file-task counters displayed in workspace overview cards."""

    init_count: int = Field(ge=0)
    process_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)


class OcrFileListItemOut(BaseModel):
    """One task row rendered in file OCR task list."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    file_name: str | None
    ocr_type: str
    status: str
    file_size: int | None = Field(default=None, ge=0)
    object_key: str
    page_count: int | None = Field(default=None, ge=0)
    create_at: datetime | None
    update_at: datetime | None


class OcrFileListPageOut(BaseModel):
    """Paginated response body for OCR task list."""

    items: list[OcrFileListItemOut]
    total: int = Field(ge=0)


class OcrFileCreateFileIn(BaseModel):
    """One file metadata item after successful S3 upload."""

    file_name: str = Field(min_length=1, max_length=256)
    file_size: int = Field(ge=0, le=50 * 1024 * 1024)
    object_key: str = Field(min_length=1, max_length=1024)


class OcrFileCreateIn(BaseModel):
    """Batch create payload for OCR tasks."""

    ocr_type: Literal["PADDLE_OCR", "MINERU"] = Field()
    files: list[OcrFileCreateFileIn] = Field(min_length=1, max_length=50)


class OcrFileBatchCreateOut(BaseModel):
    """Batch create response containing created rows."""

    items: list[OcrFileListItemOut]
    total: int = Field(ge=0)


class OcrFileLogItemOut(BaseModel):
    """One ``ocr_file_log`` row for the task drawer (DB uses ``start_at``/``finish_at``)."""

    id: uuid.UUID
    create_at: datetime
    update_at: datetime | None
    status: str
    remark: str | None


class OcrFileLogListPageOut(BaseModel):
    """Paginated OCR run logs for a single ``ocr_file``."""

    items: list[OcrFileLogItemOut]
    total: int = Field(ge=0)


class OcrFileMarkdownPageOut(BaseModel):
    """One OCR result page returned for the task detail drawer."""

    page_index: int | None = None
    markdown_text: str | None = None
    images: dict[str, str] | None = None


class OcrFileMarkdownPagesOut(BaseModel):
    """Full markdown-pages payload for one ``ocr_file`` row."""

    file_id: uuid.UUID
    ocr_type: str
    pages: list[OcrFileMarkdownPageOut]
