"""Orchestrates AI completions with retries and SSE-friendly streaming."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import orjson

from app.llm.domain.models import ChatCallParams, ChatMessage, ProviderKind
from app.llm.strategies import get_strategy
from app.llm.strategies.base import ChatCompletionStrategy
from app.config import settings
from app.exceptions import AppError

log = logging.getLogger(__name__)

_RETRIABLE_CODES = frozenset(  # ``AppError`` codes eligible for exponential backoff retries.
    {
        "ai.upstream.rate_limited",
        "ai.upstream.timeout",
        "ai.upstream.connection",
        "ai.upstream.unavailable",
        "ai.upstream.error",
    }
)


def build_openai_messages(
    *,
    system_prompt: str | None,
    user_prompt: str | None,
    messages: list[ChatMessage],
) -> list[dict[str, str]]:
    """Flatten prompts into OpenAI-compatible role/content chat arrays."""

    out: list[dict[str, str]] = []
    if system_prompt is not None and system_prompt != "":
        out.append({"role": "system", "content": system_prompt})
    for m in messages:
        out.append({"role": m.role, "content": m.content})
    if user_prompt is not None and user_prompt != "":
        out.append({"role": "user", "content": user_prompt})
    return out


class ChatService:
    """Facade delegating to provider strategies with retry/backoff."""

    async def _complete_with_retry(self, strategy: ChatCompletionStrategy, params: ChatCallParams) -> dict[str, Any]:
        """Call ``strategy.complete`` with exponential backoff on retriable ``AppError`` codes."""

        delay = 0.5
        last: AppError | None = None
        for attempt in range(settings.ai_retry_max_attempts):
            try:
                return await strategy.complete(params)
            except AppError as e:
                last = e
                if e.code not in _RETRIABLE_CODES or attempt >= settings.ai_retry_max_attempts - 1:
                    raise
                log.warning(
                    "ai complete retry attempt=%s/%s code=%s",
                    attempt + 1,
                    settings.ai_retry_max_attempts,
                    e.code,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)
        assert last is not None
        raise last

    async def complete(
        self,
        *,
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform non-streaming completion via configured strategy."""

        strategy = get_strategy(provider_kind)
        params = ChatCallParams(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=build_openai_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages or [],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        return await self._complete_with_retry(strategy, params)

    async def complete_messages(
        self,
        *,
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming completion using a caller-built OpenAI-style ``messages`` array."""

        strategy = get_strategy(provider_kind)
        params = ChatCallParams(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        return await self._complete_with_retry(strategy, params)

    async def stream_chunks(
        self,
        *,
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield upstream chunks from streaming-capable strategies."""

        strategy = get_strategy(provider_kind)
        params = ChatCallParams(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=build_openai_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages or [],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        async for chunk in strategy.stream(params):
            yield chunk

    async def stream_chunks_messages(
        self,
        *,
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream completion chunks using a caller-built OpenAI-style ``messages`` array."""

        strategy = get_strategy(provider_kind)
        params = ChatCallParams(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        async for chunk in strategy.stream(params):
            yield chunk

    async def stream_sse_lines(
        self,
        *,
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncIterator[bytes]:
        """Emit SSE-formatted ``data:`` lines ending with ``[DONE]``."""

        async for chunk in self.stream_chunks(
            provider_kind=provider_kind,
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        ):
            payload = orjson.dumps(chunk)
            yield b"data: " + payload + b"\n\n"
        yield b"data: [DONE]\n\n"


chat_service = ChatService()  # Shared singleton used by FastAPI routers.
