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
