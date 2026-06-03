"""SQL-backed memory retrieve strategy."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.memory_store import AgentMemoryStore
from app.agent.memory.hits import MemoryHit


def format_memory_hits_for_planner(hits: list[MemoryHit]) -> str:
    """Format retrieved hits as planner prefix text."""

    if not hits:
        return ""
    lines = [f"- [{h.kind}/{h.source}] {h.content[:400]}" for h in hits[:10]]
    return "已知记忆：\n" + "\n".join(lines)


class SqlMemoryRetrieveStrategy:
    """Retrieve from ``agent_long_term_memory`` and message fallback."""

    def __init__(self, store: AgentMemoryStore | None = None) -> None:
        self._store = store or AgentMemoryStore()

    async def retrieve(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        query_text: str,
        limit: int | None = None,
    ) -> list[MemoryHit]:
        """Delegate to ``AgentMemoryStore.retrieve``."""

        return await self._store.retrieve(
            session,
            workspace_id=workspace_id,
            session_id=session_id,
            query_text=query_text,
            limit=limit,
        )

    async def build_planner_context(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        query_text: str,
        hits: list[MemoryHit],
    ) -> str:
        """SQL backend: format hits only (no profile table)."""

        _ = session, workspace_id, session_id, query_text
        return format_memory_hits_for_planner(hits)
