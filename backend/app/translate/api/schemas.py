"""HTTP schemas for document translation APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocTranslateJobListItemOut(BaseModel):
    """One row in the translation job table."""

    id: uuid.UUID
    title: str | None
    file_name: str | None
    file_ext: str
    source_lang: str
    target_lang: str
    source_object_key: str
    result_object_key: str | None = None
    segment_total: int
    segment_done: int
    status: str
    progress: int
    create_at: datetime | None
    update_at: datetime | None


class DocTranslateJobListOut(BaseModel):
    """Offset-paginated job list with optional filters."""

    items: list[DocTranslateJobListItemOut]
    total: int = 0


class DocTranslateJobDetailOut(DocTranslateJobListItemOut):
    """Job detail including error and download key."""

    model_id: uuid.UUID
    ocr_file_id: uuid.UUID | None = None
    error_code: str | None = None
    error_message: str | None = None


class DocTranslateSegmentOut(BaseModel):
    """One paragraph for side-by-side UI."""

    id: uuid.UUID
    seq: int
    source_text: str
    translated_text: str | None = None
    status: str


class DocTranslateSegmentListOut(BaseModel):
    """Ordered segments for one job."""

    segments: list[DocTranslateSegmentOut]


class DocTranslateJobCreateOut(BaseModel):
    """Response after enqueueing a new translation job."""

    id: uuid.UUID
    status: str
