"""SQLAlchemy models for workspace-scoped knowledge bases (dataset_* tables)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.core.infrastructure.db.base import Base


class Dataset(Base):
    """Knowledge base container for uploaded documents and retrieval configuration."""

    __tablename__ = "dataset"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(255), nullable=False, server_default="vendor")
    permission: Mapped[str] = mapped_column(String(255), nullable=False, server_default="only_me")
    data_source_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    indexing_technique: Mapped[str | None] = mapped_column(String(255), nullable=True)
    index_struct: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_model_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    keyword_number: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="10")
    collection_binding_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    retrieval_model: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    chunk_structure: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @staticmethod
    def gen_collection_name(dataset_id: uuid.UUID) -> str:
        """Build vector collection name aligned with Dify naming."""

        normalized = str(dataset_id).replace("-", "_")
        prefix = settings.dataset_vector_index_name_prefix
        return f"{prefix}_{normalized}_Node"


class DatasetProcessRule(Base):
    """Chunking and preprocessing rules snapshot for a dataset."""

    __tablename__ = "dataset_process_rule"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(255), nullable=False, server_default="automatic")
    rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class DatasetUploadFile(Base):
    """Uploaded source file metadata for dataset ingestion."""

    __tablename__ = "dataset_upload_file"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )


class DatasetDocument(Base):
    """One ingested file within a knowledge base."""

    __tablename__ = "dataset_document"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    data_source_type: Mapped[str] = mapped_column(String(255), nullable=False)
    data_source_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_process_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    batch: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_from: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexing_status: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="waiting"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_paused: Mapped[bool | None] = mapped_column(Boolean, nullable=True, server_default=text("false"))
    doc_form: Mapped[str] = mapped_column(String(255), nullable=False, server_default="text_model")
    doc_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    doc_language: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexing_latency: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parsing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleaning_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    splitting_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DatasetDocumentSegment(Base):
    """Text chunk belonging to a dataset document."""

    __tablename__ = "dataset_document_segment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    keywords: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    index_node_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    index_node_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(String(255), nullable=False, server_default="waiting")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DatasetChildChunk(Base):
    """Child chunk used for retrieval in parent-child chunking mode."""

    __tablename__ = "dataset_child_chunk"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    segment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    index_node_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    index_node_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(255), nullable=False, server_default="automatic")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DatasetKeywordTable(Base):
    """Inverted keyword index for economy-mode retrieval."""

    __tablename__ = "dataset_keyword_table"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    keyword_table: Mapped[str] = mapped_column(Text, nullable=False)
    data_source_type: Mapped[str] = mapped_column(String(255), nullable=False, server_default="database")


class DatasetEmbedding(Base):
    """Cached embedding vectors keyed by model and content hash."""

    __tablename__ = "dataset_embedding"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="text-embedding-ada-002")
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class DatasetCollectionBinding(Base):
    """Maps embedding model to a shared vector collection name."""

    __tablename__ = "dataset_collection_binding"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="dataset")
    collection_name: Mapped[str] = mapped_column(String(64), nullable=False)
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class DatasetQuery(Base):
    """Recorded hit-testing query for a dataset."""

    __tablename__ = "dataset_query"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_role: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
