"""Embedding cache backed by dataset_embedding table."""

from __future__ import annotations

import hashlib
import struct
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.db.models import DatasetEmbedding
from app.exceptions import AppError
from app.llm.domain.models import EmbeddingCallParams
from app.llm.strategies.embedding import EmbeddingStrategy


def content_hash(text: str) -> str:
    """Return SHA-256 hex digest for embedding cache lookup."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack_embedding(vector: list[float]) -> bytes:
    """Serialize embedding floats to bytes for LargeBinary storage."""

    return struct.pack(f"{len(vector)}f", *[float(v) for v in vector])


def unpack_embedding(data: bytes) -> list[float]:
    """Deserialize bytes stored in dataset_embedding.embedding."""

    if not data or len(data) % 4 != 0:
        return []
    count = len(data) // 4
    return list(struct.unpack(f"{count}f", data))


async def load_cached_embeddings(
    session: AsyncSession,
    *,
    provider_name: str,
    model_name: str,
    hashes: list[str],
) -> dict[str, list[float]]:
    """Load cached vectors keyed by content hash."""

    if not hashes:
        return {}
    unique_hashes = list(dict.fromkeys(hashes))
    stmt = select(DatasetEmbedding).where(
        DatasetEmbedding.provider_name == provider_name.strip(),
        DatasetEmbedding.model_name == model_name.strip(),
        DatasetEmbedding.hash.in_(unique_hashes),
    )
    rows = list((await session.scalars(stmt)).all())
    cached: dict[str, list[float]] = {}
    for row in rows:
        vec = unpack_embedding(row.embedding)
        if vec:
            cached[row.hash] = vec
    return cached


async def save_cached_embedding(
    session: AsyncSession,
    *,
    provider_name: str,
    model_name: str,
    text_hash: str,
    vector: list[float],
) -> None:
    """Persist one embedding row; ignore duplicate key races."""

    existing = await session.scalar(
        select(DatasetEmbedding).where(
            DatasetEmbedding.provider_name == provider_name.strip(),
            DatasetEmbedding.model_name == model_name.strip(),
            DatasetEmbedding.hash == text_hash,
        )
    )
    if existing is not None:
        return
    session.add(
        DatasetEmbedding(
            id=uuid.uuid4(),
            provider_name=provider_name.strip(),
            model_name=model_name.strip(),
            hash=text_hash,
            embedding=pack_embedding(vector),
        )
    )


async def embed_texts_with_cache(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    provider_name: str,
    model_name: str,
    texts: list[str],
    batch_size: int = 16,
    embedder: Any | None = None,
) -> list[list[float]]:
    """Embed texts using dataset_embedding cache and optional injectable embedder."""

    if not texts:
        return []

    provider = provider_name.strip()
    model = model_name.strip()
    hashes = [content_hash(text) for text in texts]
    cached = await load_cached_embeddings(
        session,
        provider_name=provider,
        model_name=model,
        hashes=hashes,
    )

    results: list[list[float] | None] = [None] * len(texts)
    miss_indices: list[int] = []
    for index, text_hash in enumerate(hashes):
        hit = cached.get(text_hash)
        if hit is not None:
            results[index] = hit
        else:
            miss_indices.append(index)

    if not miss_indices:
        return [vec for vec in results if vec is not None]

    from app.dataset.service.embedding_resolver import resolve_embedding_model

    resolved = await resolve_embedding_model(
        session,
        workspace_id=workspace_id,
        provider_name=provider,
        model_name=model,
    )
    strategy = embedder or EmbeddingStrategy()
    miss_texts = [texts[index] for index in miss_indices]
    fetched: list[list[float]] = []
    for start in range(0, len(miss_texts), batch_size):
        batch = miss_texts[start : start + batch_size]
        result = await strategy.embed(resolved, EmbeddingCallParams(input=batch))
        batch_vectors: list[list[float]] = []
        for item in sorted(result.data, key=lambda x: int(x.get("index", 0))):
            batch_vectors.append(list(item.get("embedding") or []))
        if len(batch_vectors) != len(batch):
            raise AppError("dataset.embedding_failed", "Embedding 返回数量不匹配。", 502)
        fetched.extend(batch_vectors)

    for index, vector in zip(miss_indices, fetched, strict=True):
        results[index] = vector
        await save_cached_embedding(
            session,
            provider_name=provider,
            model_name=model,
            text_hash=hashes[index],
            vector=vector,
        )

    return [vec for vec in results if vec is not None]
