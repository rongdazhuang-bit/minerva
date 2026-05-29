"""Tests for TextChatStrategy and direct URL posting."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.llm.domain.models import TextChatCallParams, TextChatResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies import text_chat as text_chat_module
from app.llm.strategies.http_common import normalize_endpoint_url
from app.llm.strategies.text_chat import TextChatStrategy


def test_normalize_endpoint_url_keeps_full_configured_url() -> None:
    """Database URL is complete and must not be rewritten."""

    assert (
        normalize_endpoint_url("https://ark.cn-beijing.volces.com/api/v3/responses/")
        == "https://ark.cn-beijing.volces.com/api/v3/responses"
    )


def test_text_chat_complete_posts_to_configured_full_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strategy POSTs directly to resolved.endpoint_url."""

    captured: dict[str, Any] = {}

    async def fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "chatcmpl-direct",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }

    monkeypatch.setattr(text_chat_module, "post_json", fake_post_json)

    resolved = ResolvedModel(
        model_id=uuid4(),
        model_name="model-a",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="key",
    )
    params = TextChatCallParams(messages=[{"role": "user", "content": "hello"}])

    result = asyncio.run(TextChatStrategy().complete(resolved, params))

    assert isinstance(result, TextChatResult)
    assert result.assistant_text() == "ok"
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["body"]["model"] == "model-a"
    assert captured["body"]["messages"][0]["content"] == "hello"
    assert captured["body"]["stream"] is False
