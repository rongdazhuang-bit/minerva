"""Tests for direct-endpoint AsyncOpenAI client used by Agent."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from openai import AsyncOpenAI

from app.agent.infrastructure.direct_endpoint_openai_client import (
    build_direct_endpoint_async_openai,
)


@pytest.mark.asyncio
async def test_direct_endpoint_client_posts_to_configured_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat completion requests must hit the configured URL without path rewriting."""

    captured: list[str] = []

    async def recording_post(self, path: str, *args, **kwargs):
        captured.append(path)
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(AsyncOpenAI, "post", recording_post)

    client = build_direct_endpoint_async_openai(
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="secret",
    )
    await client.post("/chat/completions", cast_to=dict, body={"model": "m"})

    assert captured == ["https://example.com/v1/chat/completions"]


@pytest.mark.asyncio
async def test_direct_endpoint_client_uses_root_url_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-standard configured paths are also used verbatim."""

    captured: list[str] = []

    async def recording_post(self, path: str, *args, **kwargs):
        captured.append(path)
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(AsyncOpenAI, "post", recording_post)

    client = build_direct_endpoint_async_openai(
        endpoint_url="https://example.com/custom/infer",
        api_key="secret",
    )
    await client.post("/chat/completions", cast_to=dict, body={"model": "m"})

    assert captured == ["https://example.com/custom/infer"]
