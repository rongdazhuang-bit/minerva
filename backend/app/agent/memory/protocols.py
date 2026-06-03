"""Protocols for agent memory retrieve and persist strategies."""

from __future__ import annotations

import uuid
from typing import Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory.hits import MemoryHit


class MemoryRetrieveStrategy(Protocol):
    """Recall long-term memory and build planner context."""

    async def retrieve(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        query_text: str,
        limit: int | None = None,
    ) -> list[MemoryHit]:
        """Search memory for the current turn."""

    async def build_planner_context(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        query_text: str,
        hits: list[MemoryHit],
    ) -> str:
        """Format hits and optional profile layers for the planner prompt."""


class MemoryPersistStrategy(Protocol):
    """Persist long-term memory after a successful run."""

    async def persist_turn(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        run_id: uuid.UUID,
        user_message: str,
        final_answer: str,
        model: BaseChatModel | None = None,
    ) -> None:
        """Extract and store memory for one completed turn."""
