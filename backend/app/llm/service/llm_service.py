"""Orchestrates multi-capability LLM calls with retries and SSE helpers."""

from __future__ import annotations

from app.core.log import get_logger
import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import AppError
from app.llm.domain.models import (
    ChatMessage,
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import (
    CHAT_MODEL_TAGS,
    EMBEDDING_MODEL_TAGS,
    RERANK_MODEL_TAGS,
)
from app.llm.service.model_resolver import resolve_model
from app.llm.strategies import (
    get_embedding_strategy,
    get_rerank_strategy,
    get_text_chat_strategy,
)

log = get_logger(__name__)

_RETRIABLE_CODES = frozenset(
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


class LlmService:
    """Facade resolving models and delegating to capability strategies."""

    async def _complete_with_retry(self, coro_factory):  # noqa: ANN001
        """Run blocking upstream call with exponential backoff on retriable errors."""

        delay = 0.5
        last: AppError | None = None
        for attempt in range(settings.ai_retry_max_attempts):
            try:
                return await coro_factory()
            except AppError as e:
                last = e
                if e.code not in _RETRIABLE_CODES or attempt >= settings.ai_retry_max_attempts - 1:
                    raise
                log.warning(
                    "ai complete retry attempt={}/{} code={}",
                    attempt + 1,
                    settings.ai_retry_max_attempts,
                    e.code,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)
        assert last is not None
        raise last

    async def complete_chat(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        n: int | None = None,
        stop: list[str] | str | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        allowed_tags: frozenset[str] = CHAT_MODEL_TAGS,
        excluded_tags: frozenset[str] | None = None,
    ) -> TextChatResult:
        """Non-streaming chat completion for text or translate models."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_tags=allowed_tags,
            excluded_tags=excluded_tags,
        )
        params = TextChatCallParams(
            messages=build_openai_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages or [],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            n=n,
            stop=stop,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            tools=tools,
            tool_choice=tool_choice,
            stream=False,
        )
        strategy = get_text_chat_strategy()

        async def _call() -> TextChatResult:
            return await strategy.complete(resolved, params)

        return await self._complete_with_retry(_call)

    async def stream_chat(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        n: int | None = None,
        stop: list[str] | str | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        allowed_tags: frozenset[str] = CHAT_MODEL_TAGS,
        excluded_tags: frozenset[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield upstream chat chunks (no retry)."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_tags=allowed_tags,
            excluded_tags=excluded_tags,
        )
        params = TextChatCallParams(
            messages=build_openai_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages or [],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            n=n,
            stop=stop,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            tools=tools,
            tool_choice=tool_choice,
            stream=True,
        )
        strategy = get_text_chat_strategy()
        async for chunk in strategy.stream(resolved, params):
            yield chunk

    async def stream_sse_lines(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        n: int | None = None,
        stop: list[str] | str | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        allowed_tags: frozenset[str] = CHAT_MODEL_TAGS,
        excluded_tags: frozenset[str] | None = None,
    ) -> AsyncIterator[bytes]:
        """Emit SSE-formatted data lines ending with ``[DONE]``."""

        async for chunk in self.stream_chat(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            n=n,
            stop=stop,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            tools=tools,
            tool_choice=tool_choice,
            allowed_tags=allowed_tags,
            excluded_tags=excluded_tags,
        ):
            payload = orjson.dumps(chunk)
            yield b"data: " + payload + b"\n\n"
        yield b"data: [DONE]\n\n"

    async def embed(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        params: EmbeddingCallParams,
    ) -> EmbeddingResult:
        """Non-streaming embedding for embedding-type models."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_tags=EMBEDDING_MODEL_TAGS,
        )
        strategy = get_embedding_strategy()

        async def _call() -> EmbeddingResult:
            return await strategy.embed(resolved, params)

        return await self._complete_with_retry(_call)

    async def rerank(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        params: RerankCallParams,
    ) -> RerankResult:
        """Non-streaming rerank for rerank-type models."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_tags=RERANK_MODEL_TAGS,
        )
        strategy = get_rerank_strategy()

        async def _call() -> RerankResult:
            return await strategy.rerank(resolved, params)

        return await self._complete_with_retry(_call)


llm_service = LlmService()
