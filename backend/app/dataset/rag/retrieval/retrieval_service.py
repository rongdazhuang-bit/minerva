"""Retrieval over dataset segments (semantic, keyword, hybrid)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

import jieba.analyse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.constants import (
    DEFAULT_RETRIEVAL_MODEL,
    INDEXING_TECHNIQUE_ECONOMY,
    INDEXING_TECHNIQUE_HIGH_QUALITY,
    RETRIEVAL_FULL_TEXT,
    RETRIEVAL_HYBRID,
    RETRIEVAL_SEMANTIC,
)
from app.dataset.domain.db.models import Dataset
from app.dataset.infrastructure import repository as repo
from app.dataset.infrastructure.vector.base import VectorFactory, vector_type_for_dataset
from app.dataset.service.embedding_service import embed_texts
from app.dataset.service.index_sync_service import _load_keyword_table
from app.exceptions import AppError
from app.llm.domain.models import RerankCallParams
from app.llm.service.model_resolver import _normalize_tag_set, resolve_model
from app.llm.strategies.rerank import RerankStrategy
from app.sys.model_provider.domain.constants import MODEL_TAG_RERANKING
from app.sys.model_provider.domain.db.models import SysModel


def _resolve_retrieval_config(
    dataset: Dataset,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge dataset retrieval config with optional override."""

    base = dict(dataset.retrieval_model or DEFAULT_RETRIEVAL_MODEL)
    if override:
        base.update(override)
    return base


def _distance_to_score(distance: float) -> float:
    """Convert pgvector cosine distance to a similarity-like score."""

    return max(0.0, 1.0 - float(distance))


async def _semantic_hits(
    session: AsyncSession,
    *,
    dataset: Dataset,
    query: str,
    top_k: int,
) -> list[tuple[str, float]]:
    """Return (index_node_id, score) pairs from vector search."""

    if dataset.indexing_technique != INDEXING_TECHNIQUE_HIGH_QUALITY:
        return []
    if not dataset.embedding_model or not dataset.embedding_model_provider:
        raise AppError("dataset.embedding_required", "高质量模式需要 Embedding 模型。", 422)
    vectors = await embed_texts(
        session,
        workspace_id=dataset.workspace_id,
        provider_name=dataset.embedding_model_provider,
        model_name=dataset.embedding_model,
        texts=[query],
    )
    collection = Dataset.gen_collection_name(dataset.id)
    vector = VectorFactory.build(collection, vector_type=vector_type_for_dataset(dataset))
    docs = vector.search_by_vector(vectors[0], top_k=top_k)
    hits: list[tuple[str, float]] = []
    for doc in docs:
        node_id = str((doc.metadata or {}).get("doc_id") or "")
        if not node_id:
            continue
        score = _distance_to_score(float((doc.metadata or {}).get("score") or 0.0))
        hits.append((node_id, score))
    return hits


async def _keyword_hits(
    session: AsyncSession,
    *,
    dataset: Dataset,
    query: str,
    top_k: int,
) -> list[tuple[str, float]]:
    """Return (index_node_id, score) pairs from keyword inverted index."""

    table = await _load_keyword_table(session, dataset.id)
    if not table:
        return []
    query_keywords = jieba.analyse.extract_tags(query, topK=10)
    if not query_keywords and query.strip():
        query_keywords = [query.strip()]
    scores: dict[str, float] = defaultdict(float)
    for keyword in query_keywords:
        for node_id in table.get(keyword, []):
            scores[node_id] += 1.0
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    max_score = ranked[0][1] if ranked else 1.0
    return [(node_id, score / max_score) for node_id, score in ranked[:top_k]]


def _merge_hybrid(
    semantic: list[tuple[str, float]],
    keyword: list[tuple[str, float]],
    *,
    vector_weight: float,
    keyword_weight: float,
    top_k: int,
) -> list[tuple[str, float]]:
    """Combine semantic and keyword hits with weighted scores."""

    combined: dict[str, float] = defaultdict(float)
    for node_id, score in semantic:
        combined[node_id] += score * vector_weight
    for node_id, score in keyword:
        combined[node_id] += score * keyword_weight
    ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


async def _maybe_rerank(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    query: str,
    records: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Optionally rerank retrieved records via configured rerank model."""

    if not config.get("reranking_enable"):
        return records
    rerank_cfg = config.get("reranking_model") or {}
    provider = str(rerank_cfg.get("reranking_provider_name") or "").strip()
    model_name = str(rerank_cfg.get("reranking_model_name") or "").strip()
    if not provider or not model_name:
        return records
    stmt = select(SysModel).where(
        SysModel.workspace_id == workspace_id,
        SysModel.provider_name == provider,
        SysModel.model_name == model_name,
        SysModel.enabled.is_(True),
    )
    row = await session.scalar(stmt)
    if row is None or MODEL_TAG_RERANKING not in _normalize_tag_set(row.tags):
        return records
    resolved = await resolve_model(
        session,
        workspace_id=workspace_id,
        model_id=row.id,
        allowed_tags=frozenset({MODEL_TAG_RERANKING}),
    )
    documents = [str(rec["segment"]["content"]) for rec in records]
    if not documents:
        return records
    result = await RerankStrategy().rerank(
        resolved,
        RerankCallParams(query=query, documents=documents, top_n=len(documents)),
    )
    order = sorted(result.results, key=lambda item: int(item.get("index", 0)))
    reranked: list[dict[str, Any]] = []
    for item in order:
        idx = int(item.get("index", 0))
        if idx < 0 or idx >= len(records):
            continue
        row_out = dict(records[idx])
        row_out["score"] = float(item.get("relevance_score") or row_out.get("score") or 0.0)
        reranked.append(row_out)
    return reranked or records


async def retrieve(
    session: AsyncSession,
    *,
    dataset: Dataset,
    query: str,
    retrieval_model: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve ranked segment records for one query."""

    text = query.strip()
    if not text:
        raise AppError("dataset.query_required", "请输入查询内容。", 422)
    config = _resolve_retrieval_config(dataset, retrieval_model)
    method = str(config.get("search_method") or RETRIEVAL_SEMANTIC)
    top_k = max(1, min(20, int(config.get("top_k") or 3)))
    threshold_enabled = bool(config.get("score_threshold_enabled"))
    threshold = float(config.get("score_threshold") or 0.0)

    semantic_hits: list[tuple[str, float]] = []
    keyword_hits: list[tuple[str, float]] = []
    if method in {RETRIEVAL_SEMANTIC, RETRIEVAL_HYBRID}:
        semantic_hits = await _semantic_hits(session, dataset=dataset, query=text, top_k=top_k * 2)
    if method in {RETRIEVAL_FULL_TEXT, RETRIEVAL_HYBRID} or dataset.indexing_technique == INDEXING_TECHNIQUE_ECONOMY:
        keyword_hits = await _keyword_hits(session, dataset=dataset, query=text, top_k=top_k * 2)

    if method == RETRIEVAL_HYBRID:
        weights = config.get("weights") or {}
        vector_weight = float((weights.get("vector_setting") or {}).get("vector_weight") or 0.7)
        keyword_weight = float((weights.get("keyword_setting") or {}).get("keyword_weight") or 0.3)
        merged = _merge_hybrid(
            semantic_hits,
            keyword_hits,
            vector_weight=vector_weight,
            keyword_weight=keyword_weight,
            top_k=top_k,
        )
    elif method == RETRIEVAL_FULL_TEXT:
        merged = keyword_hits[:top_k]
    else:
        merged = semantic_hits[:top_k]
        if not merged and keyword_hits:
            merged = keyword_hits[:top_k]

    node_ids = [node_id for node_id, _ in merged]
    segments = await repo.get_segments_by_node_ids(session, dataset_id=dataset.id, node_ids=node_ids)
    child_chunks = await repo.get_child_chunks_by_node_ids(
        session,
        dataset_id=dataset.id,
        node_ids=node_ids,
    )
    seg_map = {row.index_node_id: row for row in segments if row.index_node_id}
    child_map = {row.index_node_id: row for row in child_chunks if row.index_node_id}
    parent_ids = [row.segment_id for row in child_chunks]
    parent_map = await repo.get_segments_by_ids(
        session,
        dataset_id=dataset.id,
        segment_ids=parent_ids,
    )
    doc_ids = {row.document_id for row in segments}
    doc_ids.update(row.document_id for row in child_chunks)
    doc_map = await repo.get_documents_by_ids(session, dataset_id=dataset.id, document_ids=list(doc_ids))

    records: list[dict[str, Any]] = []
    for node_id, score in merged:
        if threshold_enabled and score < threshold:
            continue
        segment = seg_map.get(node_id)
        child = child_map.get(node_id)
        if child is not None:
            segment = parent_map.get(child.segment_id)
        if segment is None or not segment.enabled:
            continue
        document = doc_map.get(segment.document_id)
        if document is None or not document.enabled:
            continue
        segment_payload: dict[str, Any] = {
            "id": str(segment.id),
            "content": segment.content,
            "document_id": str(segment.document_id),
            "position": segment.position,
            "word_count": segment.word_count,
        }
        if segment.answer:
            segment_payload["answer"] = segment.answer
        if child is not None:
            segment_payload["child_content"] = child.content
        records.append(
            {
                "score": score,
                "segment": segment_payload,
                "document": {
                    "id": str(document.id),
                    "name": document.name,
                },
            }
        )

    return await _maybe_rerank(
        session,
        workspace_id=dataset.workspace_id,
        query=text,
        records=records,
        config=config,
    )
