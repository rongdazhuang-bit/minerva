from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai_api.domain.models import ChatCallParams, ChatMessage, ProviderKind
from app.ai_api.service.chat_service import build_openai_messages, chat_service
from app.ai_api.strategies import get_strategy
from app.ai_api.strategies.volcengine_placeholder import VolcenginePlaceholderStrategy
from app.exceptions import AppError
from app.main import app


def test_build_openai_messages_order() -> None:
    m = build_openai_messages(
        system_prompt="S",
        user_prompt="U",
        messages=[ChatMessage(role="user", content="h1")],
    )
    assert m[0] == {"role": "system", "content": "S"}
    assert m[1] == {"role": "user", "content": "h1"}
    assert m[2] == {"role": "user", "content": "U"}


@pytest.mark.asyncio
async def test_volcengine_placeholder_complete() -> None:
    s = VolcenginePlaceholderStrategy()
    with pytest.raises(AppError) as ei:
        await s.complete(
            ChatCallParams(
                base_url="http://x",
                api_key="k",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        )
    assert ei.value.code == "ai.provider.not_implemented"
    assert ei.value.status_code == 501


@pytest.mark.asyncio
async def test_volcengine_stream_raises() -> None:
    s = VolcenginePlaceholderStrategy()
    params = ChatCallParams(
        base_url="http://x",
        api_key="k",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
    )
    gen = s.stream(params)
    with pytest.raises(AppError) as ei:
        async for _ in gen:
            pass
    assert ei.value.code == "ai.provider.not_implemented"


def test_get_strategy_unknown() -> None:
    with pytest.raises(AppError) as ei:
        get_strategy("not-a-provider")  # type: ignore[arg-type]
    assert ei.value.code == "ai.provider.unknown"


@pytest.mark.asyncio
async def test_openai_compatible_complete_success() -> None:
    fake = MagicMock()
    fake.model_dump = MagicMock(
        side_effect=lambda mode="json": {"id": "chatcmpl-1", "object": "chat.completion", "choices": []}
    )
    create_mock = AsyncMock(return_value=fake)
    mock_client = MagicMock()
    mock_client.chat.completions.create = create_mock
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch(
        "app.ai_api.strategies.openai_compatible.AsyncOpenAI",
        return_value=mock_cm,
    ):
        from app.ai_api.strategies.openai_compatible import OpenAICompatibleStrategy

        strat = OpenAICompatibleStrategy()
        out = await strat.complete(
            ChatCallParams(
                base_url="http://litellm/v1",
                api_key="sk",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )
        )
    assert out["id"] == "chatcmpl-1"
    create_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_openai_compatible_stream_yields_chunks() -> None:
    async def fake_chunks():
        c1 = MagicMock()
        c1.model_dump = MagicMock(side_effect=lambda mode="json": {"choices": [{"index": 0}]})
        yield c1

    create_mock = AsyncMock(return_value=fake_chunks())
    mock_client = MagicMock()
    mock_client.chat.completions.create = create_mock
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch(
        "app.ai_api.strategies.openai_compatible.AsyncOpenAI",
        return_value=mock_cm,
    ):
        from app.ai_api.strategies.openai_compatible import OpenAICompatibleStrategy

        strat = OpenAICompatibleStrategy()
        out: list[dict] = []
        async for ch in strat.stream(
            ChatCallParams(
                base_url="http://litellm/v1",
                api_key="sk",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )
        ):
            out.append(ch)
    assert len(out) == 1
    assert out[0]["choices"][0]["index"] == 0


@pytest.mark.asyncio
async def test_chat_service_complete_retries_on_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ai_retry_max_attempts", 2)
    calls: list[int] = []

    async def fake_complete(_params: ChatCallParams) -> dict:
        calls.append(1)
        if len(calls) == 1:
            raise AppError("ai.upstream.rate_limited", "once", 429)
        return {"id": "ok"}

    with patch(
        "app.ai_api.service.chat_service.get_strategy",
        return_value=MagicMock(complete=fake_complete),
    ):
        out = await chat_service.complete(
            provider_kind=ProviderKind.openai_compatible,
            base_url="http://x/v1",
            api_key="k",
            model="m",
            user_prompt="hi",
        )
    assert out["id"] == "ok"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_ai_http_chat_completion_requires_auth() -> None:
    ws = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/workspaces/{ws}/ai/chat/completions",
            json={
                "base_url": "http://localhost:4000/v1",
                "api_key": "sk",
                "model": "m",
                "stream": False,
            },
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_ai_http_stream_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sse(*_a, **_kw):
        yield b"data: {}\n\n"
        yield b"data: [DONE]\n\n"

    from app.ai_api.service.chat_service import chat_service as chat_service_singleton

    monkeypatch.setattr(chat_service_singleton, "stream_sse_lines", fake_sse)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"ai-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        import jwt
        from app.config import settings

        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        wid = str(payload["wid"])
        headers = {"Authorization": f"Bearer {token}"}
        res = await ac.post(
            f"/workspaces/{wid}/ai/chat/completions",
            headers=headers,
            json={
                "base_url": "http://localhost:4000/v1",
                "api_key": "sk",
                "model": "m",
                "stream": True,
            },
        )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
