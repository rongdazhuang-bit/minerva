"""HTTP schemas for document translation APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocTranslateJobListItemOut(BaseModel):
    """One row in the translation history sidebar."""

    id: uuid.UUID
    title: str | None
    file_name: str | None
    file_ext: str
    source_lang: str
    target_lang: str
    status: str
    progress: int
    segment_total: int
    segment_done: int
    create_at: datetime | None
    update_at: datetime | None


class DocTranslateJobListOut(BaseModel):
    """Keyset-paginated job list."""

    jobs: list[DocTranslateJobListItemOut]
    next_cursor: str | None = None


class DocTranslateJobDetailOut(DocTranslateJobListItemOut):
    """Job detail including error and download key."""

    model_id: uuid.UUID
    source_object_key: str
    result_object_key: str | None = None
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
