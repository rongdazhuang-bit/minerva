"""Tests for EmbeddingStrategy and RerankStrategy."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.llm.domain.models import EmbeddingCallParams, RerankCallParams
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies import embedding as embedding_module
from app.llm.strategies import rerank as rerank_module
from app.llm.strategies.embedding import EmbeddingStrategy
from app.llm.strategies.rerank import RerankStrategy


@pytest.mark.parametrize(
    "strategy_cls,module,method,params,raw,assert_key,endpoint",
    [
        (
            EmbeddingStrategy,
            embedding_module,
            "embed",
            EmbeddingCallParams(input="hello", dimensions=8),
            {"data": [{"index": 0, "embedding": [0.1]}], "model": "emb", "usage": {"total_tokens": 1}},
            "data",
            "https://example.com/v1/embeddings",
        ),
        (
            RerankStrategy,
            rerank_module,
            "rerank",
            RerankCallParams(query="q", documents=["a", "b"], top_n=1),
            {"id": "rerank_1", "results": [{"index": 0, "relevance_score": 0.9}]},
            "results",
            "https://example.com/v1/rerank",
        ),
    ],
)
def test_blocking_strategies_post_json(
    strategy_cls: type,
    module: Any,
    method: str,
    params: Any,
    raw: dict[str, Any],
    assert_key: str,
    endpoint: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding and rerank strategies delegate to post_json and parse results."""

    captured: dict[str, Any] = {}

    async def fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return raw

    monkeypatch.setattr(module, "post_json", fake_post_json)

    resolved = ResolvedModel(
        model_id=uuid4(),
        model_name="model-x",
        endpoint_url=endpoint,
        api_key="key",
    )
    strategy = strategy_cls()
    result = asyncio.run(getattr(strategy, method)(resolved, params))

    assert captured["body"]["model"] == "model-x"
    assert len(getattr(result, assert_key)) >= 1
    assert result.raw == raw


def test_embedding_strategy_rewrites_chat_completions_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding calls must not POST to chat/completions even if misconfigured."""

    captured: dict[str, Any] = {}

    async def fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"data": [{"index": 0, "embedding": [0.1]}]}

    monkeypatch.setattr(embedding_module, "post_json", fake_post_json)

    resolved = ResolvedModel(
        model_id=uuid4(),
        model_name="bge-m3",
        endpoint_url="http://10.150.179.15:4000/v1/chat/completions",
        api_key="key",
    )
    asyncio.run(
        EmbeddingStrategy().embed(resolved, EmbeddingCallParams(input="hello", dimensions=8))
    )
    assert captured["url"] == "http://10.150.179.15:4000/v1/embeddings"
