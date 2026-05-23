"""Tests for unified OpenAI-compatible LLM runtime strategy."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

import pytest

from app.exceptions import AppError
from app.llm.domain.models import ChatCallParams, ProviderKind
from app.llm.service.chat_service import ChatService
from app.llm.strategies import get_strategy
from app.llm.strategies import openai_compatible as openai_module
from app.llm.strategies.openai_compatible import (
    OpenAICompatibleStrategy,
    normalize_openai_base_url,
)


def test_legacy_provider_kinds_resolve_to_same_strategy() -> None:
    """All supported legacy provider values should use one runtime strategy."""

    openai_strategy = get_strategy(ProviderKind.openai)

    assert isinstance(openai_strategy, OpenAICompatibleStrategy)
    assert get_strategy(ProviderKind.volcengine) is openai_strategy
    assert get_strategy(ProviderKind.aliyun) is openai_strategy
    assert get_strategy("openai") is openai_strategy
    assert get_strategy("volcengine") is openai_strategy
    assert get_strategy("aliyun") is openai_strategy


def test_unknown_provider_kind_still_fails() -> None:
    """Unsupported provider values must not silently call an upstream model."""

    with pytest.raises(AppError) as exc:
        get_strategy("unknown")

    assert exc.value.code == "ai.provider.unknown"
    assert exc.value.status_code == 400


def test_normalize_openai_base_url_trims_slashes() -> None:
    """Configured OpenAI-compatible URLs only need trailing slash cleanup."""

    assert (
        normalize_openai_base_url("https://example.com/v1/chat/completions///")
        == "https://example.com/v1/chat/completions"
    )


def test_normalize_openai_base_url_keeps_full_configured_url() -> None:
    """The database URL is already complete and must not be rewritten."""

    assert (
        normalize_openai_base_url("https://ark.cn-beijing.volces.com/api/v3/responses/")
        == "https://ark.cn-beijing.volces.com/api/v3/responses"
    )


def test_complete_posts_to_configured_full_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The strategy should POST directly to the configured complete URL."""

    captured: dict[str, Any] = {}

    class UnexpectedAsyncOpenAI:
        """Fail if the SDK path is used because it appends endpoint paths."""

        def __init__(self, **_kwargs: Any) -> None:
            """Reject construction of the SDK client in this test."""

            raise AssertionError("OpenAI SDK should not be used for full configured URLs")

    class FakeResponse:
        """Minimal httpx-like response used by the direct POST test."""

        def raise_for_status(self) -> None:
            """Pretend the upstream returned a successful status."""

        def json(self) -> dict[str, Any]:
            """Return a fake OpenAI-style completion payload."""

            return {"id": "chatcmpl-direct-url", "choices": []}

    class FakeAsyncClient:
        """Capture direct HTTP requests without contacting an upstream service."""

        def __init__(self, **kwargs: Any) -> None:
            """Store client constructor keyword arguments."""

            captured["client_kwargs"] = kwargs

        async def __aenter__(self) -> "FakeAsyncClient":
            """Return the fake client for async context manager usage."""

            return self

        async def __aexit__(self, *_args: Any) -> None:
            """No-op async context manager cleanup."""

        async def post(self, url: str, **kwargs: Any) -> FakeResponse:
            """Capture the request URL and JSON body."""

            captured["url"] = url
            captured["request_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(openai_module, "AsyncOpenAI", UnexpectedAsyncOpenAI, raising=False)
    monkeypatch.setattr(openai_module, "AsyncClient", FakeAsyncClient, raising=False)

    result = asyncio.run(
        OpenAICompatibleStrategy().complete(
            ChatCallParams(
                base_url="https://example.com/v1/chat/completions",
                api_key="key",
                model="model-a",
                messages=[{"role": "user", "content": "hello"}],
            )
        )
    )

    assert result["id"] == "chatcmpl-direct-url"
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["request_kwargs"]["headers"]["Authorization"] == "Bearer key"
    assert captured["request_kwargs"]["json"]["model"] == "model-a"


class _RecordingStrategy:
    """Minimal strategy used to verify ChatService parameter assembly."""

    def __init__(self) -> None:
        """Initialize storage for the most recent call parameters."""

        self.params: ChatCallParams | None = None

    async def complete(self, params: ChatCallParams) -> dict[str, Any]:
        """Record non-streaming parameters and return a fake completion."""

        self.params = params
        return {"id": "chatcmpl-test", "choices": []}

    async def stream(self, params: ChatCallParams):
        """Yield one fake chunk for stream tests."""

        self.params = params
        yield {"choices": [{"delta": {"content": "ok"}}]}


def test_chat_service_complete_defaults_to_openai_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Internal callers should not need to pass provider_kind."""

    recording = _RecordingStrategy()
    chat_service_module = importlib.import_module("app.llm.service.chat_service")
    monkeypatch.setattr(chat_service_module, "get_strategy", lambda provider_kind=ProviderKind.openai: recording)

    result = asyncio.run(
        ChatService().complete(
            base_url="https://example.com/v1",
            api_key="key",
            model="model-a",
            user_prompt="hello",
        )
    )

    assert result["id"] == "chatcmpl-test"
    assert recording.params is not None
    assert recording.params.model == "model-a"
    assert recording.params.messages == [{"role": "user", "content": "hello"}]
