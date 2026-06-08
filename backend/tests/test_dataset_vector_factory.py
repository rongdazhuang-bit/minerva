"""Unit tests for vector store factory and index_struct parsing."""

from __future__ import annotations

import json

import pytest

from app.dataset.infrastructure.vector.base import (
    VectorFactory,
    resolve_vector_store_type,
    vector_type_for_dataset,
)


def test_resolve_vector_store_type_reads_json_type() -> None:
    """Parse backend slug from dataset index_struct."""

    payload = json.dumps({"type": "qdrant", "vector_store": {"class_prefix": "Vector_index_abc"}})
    assert resolve_vector_store_type(payload) == "qdrant"
    assert resolve_vector_store_type(None) is None
    assert resolve_vector_store_type("{bad json") is None


def test_vector_type_for_dataset_uses_index_struct() -> None:
    """Dataset helper returns persisted vector backend."""

    dataset = type(
        "DatasetStub",
        (),
        {"index_struct": json.dumps({"type": "weaviate"})},
    )()
    assert vector_type_for_dataset(dataset) == "weaviate"


def test_vector_factory_builds_pgvector_by_default(monkeypatch) -> None:
    """Default factory branch returns pgvector store."""

    monkeypatch.setattr(
        "app.dataset.infrastructure.vector.pgvector_store.PGVectorStore._ensure_extension",
        lambda self: None,
    )
    from app.dataset.infrastructure.vector.pgvector_store import PGVectorStore

    store = VectorFactory.build("Vector_index_test")
    assert isinstance(store, PGVectorStore)
    assert store.get_type() == "pgvector"


def test_vector_factory_builds_qdrant_branch(monkeypatch) -> None:
    """Factory can instantiate qdrant store when client is available."""

    pytest.importorskip("qdrant_client")
    from app.dataset.infrastructure.vector.qdrant_store import QdrantVectorStore

    class _FakeClient:
        def collection_exists(self, _name: str) -> bool:
            return False

        def create_collection(self, **kwargs) -> None:
            return None

    monkeypatch.setattr(
        "app.dataset.infrastructure.vector.qdrant_store._qdrant_client",
        lambda: _FakeClient(),
    )
    store = VectorFactory.build("Vector_index_test", vector_type="qdrant")
    assert isinstance(store, QdrantVectorStore)
    assert store.get_type() == "qdrant"


def test_vector_factory_unknown_store_raises() -> None:
    """Unsupported backend slug raises NotImplementedError."""

    with pytest.raises(NotImplementedError, match="milvus"):
        VectorFactory.build("Vector_index_test", vector_type="milvus")
