"""Strategy protocols for LLM capability adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.llm.domain.models import (
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import ResolvedModel


class TextChatStrategy(Protocol):
    """Adapter for OpenAI Chat Completions (text and translate model types)."""

    async def complete(
        self, resolved: ResolvedModel, params: TextChatCallParams
    ) -> TextChatResult: ...

    async def stream(
        self, resolved: ResolvedModel, params: TextChatCallParams
    ) -> AsyncIterator[dict]: ...


class EmbeddingStrategy(Protocol):
    """Adapter for OpenAI Embeddings API."""

    async def embed(
        self, resolved: ResolvedModel, params: EmbeddingCallParams
    ) -> EmbeddingResult: ...


class RerankStrategy(Protocol):
    """Adapter for OpenAI-compatible rerank API."""

    async def rerank(
        self, resolved: ResolvedModel, params: RerankCallParams
    ) -> RerankResult: ...
