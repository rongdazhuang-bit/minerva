"""Unit tests for dataset embedding cache."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dataset.rag.embedding.cached_embedding import (
    content_hash,
    embed_texts_with_cache,
    pack_embedding,
    unpack_embedding,
)
from app.llm.domain.models import EmbeddingResult


def test_pack_and_unpack_embedding_roundtrip() -> None:
    """Float vectors survive binary serialization."""

    original = [0.1, -0.2, 0.3]
    restored = unpack_embedding(pack_embedding(original))
    assert len(restored) == len(original)
    for left, right in zip(original, restored, strict=True):
        assert abs(left - right) < 1e-6


def test_content_hash_is_stable() -> None:
    """Same text yields the same cache key."""

    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


@pytest.mark.asyncio
async def test_embed_texts_with_cache_skips_remote_on_hit(monkeypatch) -> None:
    """Second call with same text does not invoke embedder."""

    session = AsyncMock()
    cached_row = MagicMock()
    cached_row.hash = content_hash("cached text")
    cached_row.embedding = pack_embedding([0.5, 0.6, 0.7])

    async def scalar_side_effect(stmt):
        _ = stmt
        return cached_row

    session.scalar = AsyncMock(side_effect=scalar_side_effect)
    session.scalars = AsyncMock(return_value=MagicMock(all=lambda: [cached_row]))

    embedder = AsyncMock()
    vectors = await embed_texts_with_cache(
        session,
        workspace_id=uuid.uuid4(),
        provider_name="openai",
        model_name="text-embedding-3-small",
        texts=["cached text"],
        embedder=embedder,
    )
    assert len(vectors) == 1
    assert len(vectors[0]) == 3
    for left, right in zip([0.5, 0.6, 0.7], vectors[0], strict=True):
        assert abs(left - right) < 1e-5
    embedder.embed.assert_not_called()


@pytest.mark.asyncio
async def test_embed_texts_with_cache_calls_remote_on_miss(monkeypatch) -> None:
    """Cache miss triggers embedder and persists new row."""

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock(return_value=MagicMock(all=lambda: []))
    session.add = MagicMock()

    embedder = AsyncMock()
    embedder.embed = AsyncMock(
        return_value=EmbeddingResult(
            data=[{"index": 0, "embedding": [0.1, 0.2]}],
            model="text-embedding-3-small",
            usage=None,
            raw={},
        )
    )

    async def fake_resolve(*args, **kwargs):
        _ = args, kwargs
        return MagicMock(model_name="text-embedding-3-small", endpoint_url="http://x", api_key="k")

    monkeypatch.setattr(
        "app.dataset.service.embedding_resolver.resolve_embedding_model",
        fake_resolve,
    )

    vectors = await embed_texts_with_cache(
        session,
        workspace_id=uuid.uuid4(),
        provider_name="openai",
        model_name="text-embedding-3-small",
        texts=["new text"],
        embedder=embedder,
    )
    assert vectors == [[0.1, 0.2]]
    embedder.embed.assert_awaited_once()
    session.add.assert_called_once()
