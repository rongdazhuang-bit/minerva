"""Pydantic schemas for GraphKB CRUD APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GraphKbCreateIn(BaseModel):
    """Create an empty graph knowledge base."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    engine: str
    permission: str
    llm_model: str | None = None
    llm_model_provider: str | None = None
    embedding_model: str | None = None
    embedding_model_provider: str | None = None
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)


class GraphKbPatchIn(BaseModel):
    """Patch mutable graph fields; engine is immutable after create."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    permission: str | None = None
    llm_model: str | None = None
    llm_model_provider: str | None = None
    embedding_model: str | None = None
    embedding_model_provider: str | None = None
    member_user_ids: list[uuid.UUID] | None = None


class GraphKbOut(BaseModel):
    """Graph knowledge base list/detail response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    engine: str
    permission: str
    llm_model: str | None = None
    llm_model_provider: str | None = None
    embedding_model: str | None = None
    embedding_model_provider: str | None = None
    indexing_status: str
    created_by: uuid.UUID
    updated_by: uuid.UUID | None = None
    create_at: datetime | None = None
    update_at: datetime | None = None
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)


class GraphKbListPageOut(BaseModel):
    """Paginated graph list response."""

    items: list[GraphKbOut]
    total: int
    page: int
    page_size: int


class GraphKbPlainTextIn(BaseModel):
    """Import a plain-text document into a graph."""

    name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1)


class GraphKbDocumentOut(BaseModel):
    """One graph document list/detail row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    graph_id: uuid.UUID
    source_type: str
    name: str
    storage_key: str | None = None
    text_content: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    indexing_status: str
    error: str | None = None
    created_by: uuid.UUID
    create_at: datetime | None = None


class GraphKbDocumentListPageOut(BaseModel):
    """Paginated document list response."""

    items: list[GraphKbDocumentOut]
    total: int
    page: int
    page_size: int


class GraphKbDocumentDeleteOut(BaseModel):
    """Delete-document response including optional reindex enqueue outcome."""

    document_id: uuid.UUID
    reindex_enqueued: bool
    message: str | None = None


class GraphKbQueryIn(BaseModel):
    """Ask a question against a completed graph index."""

    query: str = Field(min_length=1)
    mode: str
    top_k: int = Field(default=5, ge=1, le=50)


class GraphKbQueryOut(BaseModel):
    """Worker answer plus citations for one query call."""

    answer: str
    citations: list[dict] = Field(default_factory=list)


class GraphKbQueryHistoryOut(BaseModel):
    """One persisted Q&A history row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    graph_id: uuid.UUID
    query: str
    mode: str
    answer: str | None = None
    citations: list | dict | None = None
    created_by: uuid.UUID
    create_at: datetime | None = None


class GraphKbQueryHistoryPageOut(BaseModel):
    """Paginated Q&A history."""

    items: list[GraphKbQueryHistoryOut]
    total: int
    page: int
    page_size: int


class GraphKbEntityOut(BaseModel):
    """One entity projection row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    graph_id: uuid.UUID
    engine_entity_id: str
    name: str
    entity_type: str | None = None
    description: str | None = None
    community_id: uuid.UUID | None = None


class GraphKbEntityListPageOut(BaseModel):
    """Paginated entity projection list."""

    items: list[GraphKbEntityOut]
    total: int
    page: int
    page_size: int


class GraphKbRelationOut(BaseModel):
    """One relation projection row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    graph_id: uuid.UUID
    from_entity_id: str
    to_entity_id: str
    relation_type: str | None = None
    description: str | None = None
    weight: float | None = None


class GraphKbRelationListPageOut(BaseModel):
    """Paginated relation projection list."""

    items: list[GraphKbRelationOut]
    total: int
    page: int
    page_size: int


class GraphKbSummaryOut(BaseModel):
    """One community / topic summary projection row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    graph_id: uuid.UUID
    engine_community_id: str
    title: str | None = None
    summary: str | None = None
    level: int | None = None
    parent_id: uuid.UUID | None = None


class GraphKbSummaryListPageOut(BaseModel):
    """Paginated summary projection list."""

    items: list[GraphKbSummaryOut]
    total: int
    page: int
    page_size: int


class GraphKbGraphViewOut(BaseModel):
    """Canvas subgraph payload (nodes + edges)."""

    nodes: list[dict]
    edges: list[dict]


class GraphKbJobOut(BaseModel):
    """Index / reindex job status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    graph_id: uuid.UUID
    kind: str
    status: str
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_by: uuid.UUID
    create_at: datetime | None = None
