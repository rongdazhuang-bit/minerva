"""Tests for OpenAI-compatible chat params including tools and tool_choice."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.domain.models import ChatCallParams, ProviderKind
from app.llm.service.chat_service import chat_service
from app.llm.strategies.openai_compatible import OpenAICompatibleStrategy


@pytest.mark.asyncio
async def test_openai_compatible_complete_passes_tools_to_create() -> None:
    """``complete`` forwards ``tools`` and ``tool_choice`` into the SDK create call."""

    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo input.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    fake = MagicMock()
    fake.model_dump = MagicMock(
        return_value={"id": "x", "object": "chat.completion", "choices": []}
    )
    create_mock = AsyncMock(return_value=fake)
    mock_client = MagicMock()
    mock_client.chat.completions.create = create_mock
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm.strategies.openai_compatible.AsyncOpenAI", return_value=mock_cm):
        strat = OpenAICompatibleStrategy()
        await strat.complete(
            ChatCallParams(
                base_url="http://litellm/v1",
                api_key="sk",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
                tool_choice="auto",
            )
        )
    kwargs = create_mock.await_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_openai_compatible_stream_passes_tools_to_create() -> None:
    """``stream`` forwards ``tools`` into the SDK create call."""

    tools = [{"type": "function", "function": {"name": "noop", "parameters": {"type": "object"}}}]

    async def fake_chunks():
        c1 = MagicMock()
        c1.model_dump = MagicMock(side_effect=lambda mode="json": {"choices": []})
        yield c1

    create_mock = AsyncMock(return_value=fake_chunks())
    mock_client = MagicMock()
    mock_client.chat.completions.create = create_mock
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm.strategies.openai_compatible.AsyncOpenAI", return_value=mock_cm):
        strat = OpenAICompatibleStrategy()
        async for _ in strat.stream(
            ChatCallParams(
                base_url="http://litellm/v1",
                api_key="sk",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
                tool_choice="required",
            )
        ):
            pass
    kwargs = create_mock.await_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "required"
    assert kwargs["stream"] is True


@pytest.mark.asyncio
async def test_chat_service_complete_messages_passes_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """``complete_messages`` builds ``ChatCallParams`` with raw messages and tools."""

    from app.config import settings

    monkeypatch.setattr(settings, "ai_retry_max_attempts", 1)
    captured: list[ChatCallParams] = []

    async def fake_complete(params: ChatCallParams) -> dict:
        captured.append(params)
        return {"id": "ok"}

    with patch(
        "app.llm.service.chat_service.get_strategy",
        return_value=MagicMock(complete=fake_complete),
    ):
        tools = [{"type": "function", "function": {"name": "n", "parameters": {"type": "object"}}}]
        out = await chat_service.complete_messages(
            provider_kind=ProviderKind.openai_compatible,
            base_url="http://x/v1",
            api_key="k",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            tool_choice="auto",
        )
    assert out["id"] == "ok"
    assert len(captured) == 1
    p = captured[0]
    assert p.messages == [{"role": "user", "content": "hi"}]
    assert p.tools == tools
    assert p.tool_choice == "auto"


@pytest.mark.asyncio
async def test_chat_service_stream_chunks_messages_yields(monkeypatch: pytest.MonkeyPatch) -> None:
    """``stream_chunks_messages`` delegates to the strategy stream with tools."""

    async def fake_stream(_params: ChatCallParams):
        yield {"x": 1}

    with patch(
        "app.llm.service.chat_service.get_strategy",
        return_value=MagicMock(stream=fake_stream),
    ):
        chunks: list[dict] = []
        async for ch in chat_service.stream_chunks_messages(
            provider_kind=ProviderKind.openai_compatible,
            base_url="http://x/v1",
            api_key="k",
            model="m",
            messages=[{"role": "user", "content": "a"}],
            tools=None,
            tool_choice=None,
        ):
            chunks.append(ch)
    assert chunks == [{"x": 1}]
