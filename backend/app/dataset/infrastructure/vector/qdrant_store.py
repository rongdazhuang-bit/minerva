"""Qdrant-backed vector storage for dataset segments."""

from __future__ import annotations

import uuid
from typing import Any

from app.config import settings
from app.dataset.infrastructure.vector.base import BaseVector
from app.dataset.rag.models import RagDocument


def _qdrant_client() -> Any:
    """Create a Qdrant client from dataset settings."""

    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise ImportError(
            "qdrant-client is required for DATASET_VECTOR_STORE=qdrant. "
            "Install with: pip install 'minerva-backend[vector]'"
        ) from exc
    url = (settings.dataset_qdrant_url or "http://127.0.0.1:6333").strip()
    api_key = (settings.dataset_qdrant_api_key or "").strip() or None
    return QdrantClient(url=url, api_key=api_key)


class QdrantVectorStore(BaseVector):
    """Store embeddings in a Qdrant collection per dataset."""

    def __init__(self, collection_name: str) -> None:
        """Bind collection name and lazy client."""

        super().__init__(collection_name)
        self._client = _qdrant_client()

    def get_type(self) -> str:
        """Return backend slug."""

        return "qdrant"

    def _ensure_collection(self, dimension: int) -> None:
        """Create collection when missing."""

        from qdrant_client.http import models

        if self._client.collection_exists(self._collection_name):
            return
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )

    @staticmethod
    def _build_payload(doc: RagDocument) -> dict[str, Any]:
        """Flatten metadata and text into Qdrant payload."""

        payload = dict(doc.metadata or {})
        payload["text"] = doc.page_content
        return payload

    @staticmethod
    def _point_id(doc: RagDocument) -> str:
        """Resolve stable point id from document metadata."""

        raw = (doc.metadata or {}).get("doc_id")
        if raw:
            return str(raw)
        return str(uuid.uuid4())

    def create(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Create collection then insert."""

        if not embeddings:
            return []
        self._ensure_collection(len(embeddings[0]))
        return self.add_texts(texts, embeddings)

    def add_texts(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Bulk upsert vectors."""

        if not texts:
            return []
        from qdrant_client.http import models

        self._ensure_collection(len(embeddings[0]))
        ids: list[str] = []
        points: list[models.PointStruct] = []
        for doc, emb in zip(texts, embeddings, strict=True):
            point_id = self._point_id(doc)
            ids.append(point_id)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=emb,
                    payload=self._build_payload(doc),
                )
            )
        self._client.upsert(collection_name=self._collection_name, points=points)
        return ids

    def delete_by_metadata_field(self, key: str, value: str) -> None:
        """Delete points whose payload field matches."""

        from qdrant_client.http import models

        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value),
                        )
                    ]
                )
            ),
        )

    def delete_collection(self) -> None:
        """Drop Qdrant collection."""

        if self._client.collection_exists(self._collection_name):
            self._client.delete_collection(self._collection_name)

    def search_by_vector(self, query_vector: list[float], *, top_k: int = 3) -> list[RagDocument]:
        """Cosine similarity search; metadata score stores distance like pgvector."""

        hits = self._client.search(
            collection_name=self._collection_name,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )
        docs: list[RagDocument] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            text = str(payload.pop("text", "") or "")
            similarity = float(hit.score or 0.0)
            metadata = payload
            metadata["score"] = max(0.0, 1.0 - similarity)
            docs.append(RagDocument(page_content=text, metadata=metadata))
        return docs
