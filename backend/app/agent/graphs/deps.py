"""Runtime dependencies injected into graph nodes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.memory_store import AgentMemoryStore


SseEmitFn = Callable[[bytes], Awaitable[None]]


@dataclass
class GraphDeps:
    """Per-run services passed into compiled graph nodes."""

    db: AsyncSession
    model: BaseChatModel
    workspace_id: uuid.UUID
    session_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    memory_store: AgentMemoryStore
    emit_sse: SseEmitFn | None = None
    temperature: float | None = None
    max_tokens: int | None = None
