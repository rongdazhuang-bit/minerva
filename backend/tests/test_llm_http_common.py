"""Tests for shared LLM HTTP helpers."""

from __future__ import annotations

import pytest
from httpx import HTTPStatusError, Request, Response

from app.exceptions import AppError
from app.llm.strategies.http_common import (
    map_upstream_error,
    normalize_endpoint_url,
    request_headers,
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


def test_map_upstream_error_unauthorized() -> None:
    """HTTP 401 maps to ai.upstream.unauthorized."""

    req = Request("POST", "https://example.com")
    resp = Response(401, request=req)
    err = HTTPStatusError("401", request=req, response=resp)
    mapped = map_upstream_error(err)
    assert isinstance(mapped, AppError)
    assert mapped.code == "ai.upstream.unauthorized"
    assert mapped.status_code == 502
