"""Weaviate-backed vector storage for dataset segments."""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.config import settings
from app.dataset.infrastructure.vector.base import BaseVector
from app.dataset.rag.models import RagDocument


def _sanitize_class_name(collection_name: str) -> str:
    """Convert collection slug into a valid Weaviate class name."""

    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", collection_name)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"C_{cleaned}"
    return cleaned[:63]


def _weaviate_client() -> Any:
    """Connect to Weaviate using dataset settings."""

    try:
        import weaviate
        from weaviate.classes.init import Auth
        from weaviate.connect import ConnectionParams
    except ImportError as exc:
        raise ImportError(
            "weaviate-client is required for DATASET_VECTOR_STORE=weaviate. "
            "Install with: pip install 'minerva-backend[vector]'"
        ) from exc
    endpoint = (settings.dataset_weaviate_endpoint or "http://127.0.0.1:8080").strip()
    api_key = (settings.dataset_weaviate_api_key or "").strip()
    client = weaviate.WeaviateClient(
        connection_params=ConnectionParams.from_url(endpoint),
        auth_credentials=Auth.api_key(api_key) if api_key else None,
    )
    client.connect()
    return client


class WeaviateVectorStore(BaseVector):
    """Store embeddings in a Weaviate collection per dataset."""

    def __init__(self, collection_name: str) -> None:
        """Bind logical collection and Weaviate class name."""

        super().__init__(collection_name)
        self._class_name = _sanitize_class_name(collection_name)
        self._client = _weaviate_client()
        self._collection: Any | None = None

    def get_type(self) -> str:
        """Return backend slug."""

        return "weaviate"

    def _get_collection(self, dimension: int) -> Any:
        """Return existing collection or create one."""

        if self._collection is not None:
            return self._collection
        from weaviate.classes.config import Configure, DataType, Property

        if self._client.collections.exists(self._class_name):
            self._collection = self._client.collections.get(self._class_name)
            return self._collection
        self._collection = self._client.collections.create(
            name=self._class_name,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(distance_metric="cosine"),
            properties=[
                Property(name="text", data_type=DataType.TEXT),
                Property(name="meta_json", data_type=DataType.TEXT),
                Property(name="doc_id", data_type=DataType.TEXT),
                Property(name="document_id", data_type=DataType.TEXT),
                Property(name="dataset_id", data_type=DataType.TEXT),
            ],
        )
        _ = dimension
        return self._collection

    @staticmethod
    def _doc_uuid(doc: RagDocument) -> uuid.UUID:
        """Resolve object uuid from metadata doc_id."""

        raw = (doc.metadata or {}).get("doc_id")
        if raw:
            try:
                return uuid.UUID(str(raw))
            except ValueError:
                pass
        return uuid.uuid4()

    def create(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Create class then insert."""

        if not embeddings:
            return []
        self._get_collection(len(embeddings[0]))
        return self.add_texts(texts, embeddings)

    def add_texts(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Bulk insert objects with vectors."""

        import json

        if not texts:
            return []
        collection = self._get_collection(len(embeddings[0]))
        ids: list[str] = []
        with collection.batch.dynamic() as batch:
            for doc, emb in zip(texts, embeddings, strict=True):
                doc_id = str((doc.metadata or {}).get("doc_id") or uuid.uuid4())
                ids.append(doc_id)
                meta = dict(doc.metadata or {})
                batch.add_object(
                    properties={
                        "text": doc.page_content,
                        "meta_json": json.dumps(meta, ensure_ascii=False),
                        "doc_id": doc_id,
                        "document_id": str(meta.get("document_id") or ""),
                        "dataset_id": str(meta.get("dataset_id") or ""),
                    },
                    vector=emb,
                    uuid=self._doc_uuid(doc),
                )
        return ids

    def delete_by_metadata_field(self, key: str, value: str) -> None:
        """Delete objects filtered by a top-level property."""

        if key not in {"doc_id", "document_id", "dataset_id"}:
            raise ValueError(f"Weaviate store only supports deleting by doc_id/document_id/dataset_id, got {key}")
        collection = self._get_collection(1)
        from weaviate.classes.query import Filter

        collection.data.delete_many(where=Filter.by_property(key).equal(value))

    def delete_collection(self) -> None:
        """Drop Weaviate class."""

        if self._client.collections.exists(self._class_name):
            self._client.collections.delete(self._class_name)
        self._collection = None

    def search_by_vector(self, query_vector: list[float], *, top_k: int = 3) -> list[RagDocument]:
        """Near-vector search; metadata score stores cosine distance."""

        import json

        collection = self._get_collection(len(query_vector))
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=top_k,
            return_metadata=["distance"],
        )
        docs: list[RagDocument] = []
        for obj in response.objects:
            props = obj.properties or {}
            text = str(props.get("text") or "")
            meta_raw = props.get("meta_json")
            if isinstance(meta_raw, str) and meta_raw.strip():
                try:
                    metadata = json.loads(meta_raw)
                except json.JSONDecodeError:
                    metadata = {}
            else:
                metadata = {
                    "doc_id": props.get("doc_id"),
                    "document_id": props.get("document_id"),
                    "dataset_id": props.get("dataset_id"),
                }
            distance = float(getattr(obj.metadata, "distance", 0.0) or 0.0)
            metadata["score"] = distance
            docs.append(RagDocument(page_content=text, metadata=metadata))
        return docs

    def __del__(self) -> None:
        """Close Weaviate client on teardown."""

        try:
            if hasattr(self, "_client") and self._client is not None:
                self._client.close()
        except Exception:
            pass
