"""Tests for LLM domain DTOs."""

from __future__ import annotations

from uuid import uuid4

from app.llm.domain.models import (
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import (
    CHAT_MODEL_TYPES,
    EMBEDDING_MODEL_TYPES,
    RERANK_MODEL_TYPES,
    ResolvedModel,
)


def test_text_chat_result_assistant_text() -> None:
    """TextChatResult extracts assistant content from OpenAI-shaped payload."""

    result = TextChatResult(
        choices=[{"message": {"role": "assistant", "content": "hello"}}],
        raw={"choices": [{"message": {"content": "hello"}}]},
    )
    assert result.assistant_text() == "hello"


def test_text_chat_result_empty_choices() -> None:
    """Missing choices yield empty assistant text."""

    result = TextChatResult(choices=[], raw={})
    assert result.assistant_text() == ""


def test_model_type_constants() -> None:
    """Allowed model_type sets match spec."""

    assert CHAT_MODEL_TYPES == frozenset({"text", "translate"})
    assert EMBEDDING_MODEL_TYPES == frozenset({"embedding"})
    assert RERANK_MODEL_TYPES == frozenset({"rerank"})


def test_resolved_model_fields() -> None:
    """ResolvedModel carries upstream credentials."""

    mid = uuid4()
    row = ResolvedModel(
        model_id=mid,
        model_name="gpt-4o-mini",
        model_type="text",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="secret",
    )
    assert row.model_id == mid
    assert row.model_name == "gpt-4o-mini"


def test_embedding_and_rerank_params() -> None:
    """Embedding and rerank params accept spec fields."""

    emb = EmbeddingCallParams(input="hello", dimensions=1536)
    assert emb.encoding_format == "float"
    rerank = RerankCallParams(query="q", documents=["a", "b"], top_n=2)
    assert rerank.top_n == 2
    assert EmbeddingResult(data=[], raw={}).data == []
    assert RerankResult(results=[], raw={}).results == []
