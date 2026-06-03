"""Tests for mem0 embedder request/response logging."""

from __future__ import annotations

import logging

from app.agent.memory.mem0.logging_embedder import (
    LoggingEmbedderWrapper,
    build_embedder_request_body,
    log_embedder_request,
    log_embedder_response,
    summarize_embedding_vectors,
    wrap_embedder_with_logging,
)


class _FakeConfig:
    """Minimal embedder config for logging tests."""

    model = "bge-m3"
    openai_base_url = "http://127.0.0.1:4000/v1"
    embedding_dims = 4096


class _FakeEmbedder:
    """Fake mem0 embedder that returns deterministic vectors."""

    def __init__(self) -> None:
        """Initialize fake config and dimension-pass flag."""

        self.config = _FakeConfig()
        self._pass_dimensions_to_api = True

    def embed(self, text: str, memory_action: str | None = None) -> list[float]:
        """Return a single fake embedding vector."""

        _ = memory_action
        return [0.1, 0.2, 0.3]

    def embed_batch(self, texts: list[str], memory_action: str = "add") -> list[list[float]]:
        """Return one fake vector per input text."""

        _ = memory_action
        return [[float(index), 0.0, 0.0] for index, _ in enumerate(texts)]


def test_summarize_embedding_vectors_omits_full_arrays() -> None:
    """Response summaries include dims and preview only."""

    summary = summarize_embedding_vectors([[0.111111, 0.222222, 0.333333]])
    assert summary["embedding_count"] == 1
    assert summary["data"][0]["embedding_dims"] == 3
    assert summary["data"][0]["embedding_preview"] == [0.111111, 0.333333]


def test_build_embedder_request_body_truncates_batch_inputs() -> None:
    """Batch request logs show count and first few inputs."""

    inner = _FakeEmbedder()
    body = build_embedder_request_body(
        inner=inner,
        inputs=[f"text-{index}" for index in range(7)],
        memory_action="search",
    )
    assert body["input_count"] == 7
    assert body["input_truncated"] == 2
    assert body["dimensions"] == 4096


def test_logging_wrapper_emits_request_and_response(caplog) -> None:
    """Wrapper logs one request/response pair per embed call."""

    caplog.set_level(logging.INFO)
    wrapped = wrap_embedder_with_logging(_FakeEmbedder())
    assert isinstance(wrapped, LoggingEmbedderWrapper)
    vector = wrapped.embed("hello", "search")
    assert vector == [0.1, 0.2, 0.3]
    messages = [record.message for record in caplog.records]
    assert any("mem0 embedder request" in message for message in messages)
    assert any("mem0 embedder response" in message for message in messages)


def test_log_helpers_include_url_and_body(caplog) -> None:
    """Standalone log helpers include URL and JSON body."""

    caplog.set_level(logging.INFO)
    inner = _FakeEmbedder()
    log_embedder_request(inner=inner, inputs=["ping"], memory_action="probe")
    log_embedder_response(inner=inner, vectors=[[0.0, 1.0]], extra={"status_code": 200})
    joined = "\n".join(record.message for record in caplog.records)
    assert "http://127.0.0.1:4000/v1/embeddings" in joined
    assert "memory_action" in joined
    assert "status_code" in joined
