"""Vector store abstractions (Dify-compatible surface)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from app.dataset.rag.models import RagDocument


def resolve_vector_store_type(index_struct: str | None) -> str | None:
    """Parse stored vector backend type from dataset ``index_struct`` JSON."""

    if not index_struct:
        return None
    try:
        payload = json.loads(index_struct)
    except json.JSONDecodeError:
        return None
    raw = payload.get("type")
    return str(raw).lower() if raw else None


def vector_type_for_dataset(dataset: Any) -> str | None:
    """Return vector backend slug persisted on a dataset row."""

    return resolve_vector_store_type(getattr(dataset, "index_struct", None))


class BaseVector(ABC):
    """Abstract vector index for one dataset collection."""

    def __init__(self, collection_name: str) -> None:
        """Store logical collection name."""

        self._collection_name = collection_name

    @property
    def collection_name(self) -> str:
        """Return collection identifier."""

        return self._collection_name

    @abstractmethod
    def get_type(self) -> str:
        """Return vector backend type slug."""

    @abstractmethod
    def create(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Create collection and insert initial vectors."""

    @abstractmethod
    def add_texts(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Insert vectors into an existing collection."""

    @abstractmethod
    def delete_by_metadata_field(self, key: str, value: str) -> None:
        """Remove vectors matching metadata field."""

    def delete_collection(self) -> None:
        """Drop underlying collection storage when the backend supports it."""

        raise NotImplementedError

    @abstractmethod
    def search_by_vector(self, query_vector: list[float], *, top_k: int = 3) -> list[RagDocument]:
        """Similarity search by embedding vector."""


class VectorFactory:
    """Select concrete vector backend from settings."""

    @staticmethod
    def build(collection_name: str, *, vector_type: str | None = None) -> BaseVector:
        """Instantiate vector store for ``collection_name``."""

        from app.config import settings

        store_type = (vector_type or settings.dataset_vector_store or "pgvector").lower()
        if store_type == "pgvector":
            from app.dataset.infrastructure.vector.pgvector_store import PGVectorStore

            return PGVectorStore(collection_name)
        if store_type == "qdrant":
            from app.dataset.infrastructure.vector.qdrant_store import QdrantVectorStore

            return QdrantVectorStore(collection_name)
        if store_type == "weaviate":
            from app.dataset.infrastructure.vector.weaviate_store import WeaviateVectorStore

            return WeaviateVectorStore(collection_name)
        raise NotImplementedError(f"Vector store '{store_type}' is not implemented yet.")
