"""Pydantic schemas for dataset APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DatasetListItemOut(BaseModel):
    """One row in the knowledge base list table."""

    id: uuid.UUID
    name: str
    description: str | None = None
    indexing_technique: str | None = None
    document_count: int = 0
    create_at: datetime | None = None
    update_at: datetime | None = None


class DatasetListPageOut(BaseModel):
    """Paginated dataset list response."""

    items: list[DatasetListItemOut]
    total: int


class DatasetCreateIn(BaseModel):
    """Create an empty knowledge base (optional shortcut)."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class DatasetDocumentIndexingStatusOut(BaseModel):
    """Single-document indexing progress (aligned with Dify)."""

    id: uuid.UUID
    name: str
    indexing_status: str
    display_status: str
    error: str | None = None
    is_paused: bool = False
    processing_started_at: datetime | None = None
    parsing_completed_at: datetime | None = None
    cleaning_completed_at: datetime | None = None
    splitting_completed_at: datetime | None = None
    completed_at: datetime | None = None
    stopped_at: datetime | None = None
    total_segments: int = 0
    completed_segments: int = 0


class DatasetUploadOut(BaseModel):
    """Uploaded source file metadata."""

    id: uuid.UUID
    name: str
    size: int
    extension: str
    mime_type: str | None = None


class DatasetProcessRuleOut(BaseModel):
    """Default or saved process rule payload."""

    process_rule: dict[str, Any]


class DatasetIndexingEstimateIn(BaseModel):
    """Request body for chunk preview before creation."""

    file_ids: list[uuid.UUID] = Field(min_length=1)
    process_rule: dict[str, Any] | None = None
    indexing_technique: str | None = None
    doc_form: str | None = None
    preview_file_id: uuid.UUID | None = None


class DatasetSegmentPreviewOut(BaseModel):
    """One preview segment."""

    content: str
    word_count: int


class DatasetFilePreviewOut(BaseModel):
    """Preview result for one uploaded file."""

    file_id: str
    file_name: str
    segment_count: int
    segments: list[DatasetSegmentPreviewOut]


class DatasetIndexingEstimateOut(BaseModel):
    """Aggregate preview response."""

    total_segments: int
    total_chars: int
    preview_file_count: int
    previews: list[DatasetFilePreviewOut]


class DatasetInitIn(BaseModel):
    """Create knowledge base with uploaded documents."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    indexing_technique: str
    doc_form: str = "text_model"
    file_ids: list[uuid.UUID] = Field(min_length=1)
    process_rule: dict[str, Any] | None = None
    retrieval_model: dict[str, Any] | None = None
    embedding_model: str | None = None
    embedding_model_provider: str | None = None


class DatasetInitDocumentOut(BaseModel):
    """Document row returned from init."""

    id: uuid.UUID
    name: str
    indexing_status: str
    batch: str


class DatasetInitDatasetOut(BaseModel):
    """Dataset summary returned from init."""

    id: uuid.UUID
    name: str
    description: str | None = None
    indexing_technique: str | None = None
    collection_name: str | None = None


class DatasetInitOut(BaseModel):
    """Init wizard completion payload."""

    dataset: DatasetInitDatasetOut
    batch: str
    documents: list[DatasetInitDocumentOut]
    indexing_task_id: str | None = None


class DatasetBatchIndexingStatusItemOut(BaseModel):
    """One document indexing progress row."""

    id: uuid.UUID
    name: str
    indexing_status: str
    error: str | None = None
    completed_at: datetime | None = None
    processing_started_at: datetime | None = None


class DatasetBatchIndexingStatusOut(BaseModel):
    """Batch indexing progress for Step 3 polling."""

    batch: str
    total: int
    completed: int
    failed: int
    processing: int
    documents: list[DatasetBatchIndexingStatusItemOut]


class DatasetDetailOut(BaseModel):
    """Knowledge base detail response."""

    id: uuid.UUID
    name: str
    description: str | None = None
    indexing_technique: str | None = None
    embedding_model: str | None = None
    embedding_model_provider: str | None = None
    retrieval_model: dict[str, Any] | None = None
    chunk_structure: str | None = None
    document_count: int = 0
    process_rule_id: uuid.UUID | None = None
    process_rule: dict[str, Any] | None = None
    create_at: datetime | None = None
    update_at: datetime | None = None


class DatasetPatchIn(BaseModel):
    """Patch knowledge base settings."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    indexing_technique: str | None = None
    embedding_model: str | None = None
    embedding_model_provider: str | None = None
    retrieval_model: dict[str, Any] | None = None
    process_rule: dict[str, Any] | None = None


class DatasetDocumentOut(BaseModel):
    """One document in list/detail responses."""

    id: uuid.UUID
    name: str
    position: int
    indexing_status: str
    display_status: str
    enabled: bool
    archived: bool
    is_paused: bool
    doc_form: str = "text_model"
    word_count: int | None = None
    hit_count: int = 0
    error: str | None = None
    batch: str
    create_at: datetime | None = None
    update_at: datetime | None = None
    completed_at: datetime | None = None
    file_id: str | None = None
    process_rule_id: uuid.UUID | None = None
    process_rule: dict[str, Any] | None = None


class DatasetDocumentListPageOut(BaseModel):
    """Paginated document list."""

    items: list[DatasetDocumentOut]
    total: int


class DatasetDocumentAppendIn(BaseModel):
    """Append documents to an existing knowledge base."""

    file_ids: list[uuid.UUID] = Field(min_length=1)
    process_rule: dict[str, Any] | None = None


class DatasetDocumentAppendOut(BaseModel):
    """Append documents response."""

    batch: str
    documents: list[DatasetDocumentOut]
    indexing_task_id: str | None = None


class DatasetDocumentPatchIn(BaseModel):
    """Patch one document (rename or segment settings)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    process_rule: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> DatasetDocumentPatchIn:
        """Require at least one mutable field in the request body."""

        if self.name is None and self.process_rule is None:
            raise ValueError("name or process_rule required")
        return self


class DatasetRetryOut(BaseModel):
    """Dataset-level retry response."""

    retried_count: int
    document_ids: list[uuid.UUID]


class DatasetSegmentOut(BaseModel):
    """One segment row."""

    id: uuid.UUID
    position: int
    content: str
    answer: str | None = None
    word_count: int
    tokens: int
    enabled: bool
    status: str
    hit_count: int
    child_count: int = 0
    create_at: datetime | None = None
    update_at: datetime | None = None


class DatasetChildChunkOut(BaseModel):
    """One child chunk under a parent segment."""

    id: uuid.UUID
    position: int
    content: str
    word_count: int
    index_node_id: str | None = None
    create_at: datetime | None = None
    update_at: datetime | None = None


class DatasetChildChunkListOut(BaseModel):
    """Child chunks for one segment."""

    items: list[DatasetChildChunkOut]


class DatasetChildChunkCreateIn(BaseModel):
    """Create one child chunk under a parent segment."""

    content: str = Field(min_length=1)


class DatasetChildChunkPatchIn(BaseModel):
    """Update child chunk content."""

    content: str = Field(min_length=1)


class DatasetSegmentListPageOut(BaseModel):
    """Paginated segment list."""

    items: list[DatasetSegmentOut]
    total: int


class DatasetSegmentCreateIn(BaseModel):
    """Create one manual segment."""

    content: str = Field(min_length=1)


class DatasetSegmentPatchIn(BaseModel):
    """Patch segment content."""

    content: str = Field(min_length=1)


class HitTestingIn(BaseModel):
    """Hit testing request body."""

    query: str = Field(min_length=1)
    retrieval_model: dict[str, Any] | None = None


class HitTestingRecordOut(BaseModel):
    """One retrieval hit."""

    score: float
    segment: dict[str, Any]
    document: dict[str, Any]


class HitTestingOut(BaseModel):
    """Hit testing response."""

    query: str
    records: list[HitTestingRecordOut]


class DatasetQueryOut(BaseModel):
    """Historical query row."""

    id: uuid.UUID
    content: str
    source: str
    create_at: datetime | None = None


class DatasetQueryListPageOut(BaseModel):
    """Paginated query history."""

    items: list[DatasetQueryOut]
    total: int
