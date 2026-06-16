"""Tests for shared LLM HTTP helpers."""

from __future__ import annotations

import pytest
from httpx import HTTPStatusError, Request, Response

from app.exceptions import AppError
from app.llm.strategies.http_common import (
    map_upstream_error,
    normalize_endpoint_url,
    request_headers,
    resolve_embeddings_url,
    resolve_rerank_url,
)


def test_normalize_endpoint_url_trims_slashes() -> None:
    """Configured URLs only need trailing slash cleanup."""

    assert (
        normalize_endpoint_url("https://example.com/v1/chat/completions///")
        == "https://example.com/v1/chat/completions"
    )


def test_request_headers_bearer() -> None:
    """Authorization uses Bearer scheme."""

    headers = request_headers("key-abc")
    assert headers["Authorization"] == "Bearer key-abc"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (
            "http://10.150.179.15:4000/v1/chat/completions",
            "http://10.150.179.15:4000/v1/embeddings",
        ),
        ("http://127.0.0.1:4000/v1", "http://127.0.0.1:4000/v1/embeddings"),
        ("http://127.0.0.1:4000", "http://127.0.0.1:4000/v1/embeddings"),
        (
            "https://example.com/v1/embeddings",
            "https://example.com/v1/embeddings",
        ),
        (
            "https://ark.cn-beijing.volces.com/api/v3/responses",
            "https://ark.cn-beijing.volces.com/api/v3/responses",
        ),
    ],
)
def test_resolve_embeddings_url(configured: str, expected: str) -> None:
    """Embedding URL resolver fixes chat endpoints and bare LiteLLM bases."""

    assert resolve_embeddings_url(configured) == expected


def test_resolve_rerank_url_from_chat_endpoint() -> None:
    """Rerank URL resolver rewrites chat/completions sibling paths."""

    assert (
        resolve_rerank_url("https://example.com/v1/chat/completions")
        == "https://example.com/v1/rerank"
    )


def test_map_upstream_error_unauthorized() -> None:
    """HTTP 401 maps to ai.upstream.unauthorized."""

    req = Request("POST", "https://example.com")
    resp = Response(401, request=req)
    err = HTTPStatusError("401", request=req, response=resp)
    mapped = map_upstream_error(err)
    assert isinstance(mapped, AppError)
    assert mapped.code == "ai.upstream.unauthorized"
    assert mapped.status_code == 502
