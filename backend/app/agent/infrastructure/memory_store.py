"""SQL-backed long-term memory retrieval and persistence for agent runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import AgentLongTermMemory, AgentMessage
from app.config import settings


@dataclass(frozen=True)
class MemoryHit:
    """One memory item returned to the planner or executor."""

    content: str
    kind: str
    source: str
    key: str | None = None
    memory_id: uuid.UUID | None = None


class AgentMemoryStore:
    """Retrieve and upsert long-term memory rows plus message fallback."""

    async def retrieve(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        query_text: str,
        limit: int | None = None,
    ) -> list[MemoryHit]:
        """Search structured memory first, then recent messages by ILIKE."""

        cap = limit if limit is not None else settings.agent_memory_retrieve_limit
        q = (query_text or "").strip()
        pattern = f"%{q}%" if q else "%"
        hits: list[MemoryHit] = []

        scope = or_(
            AgentLongTermMemory.session_id.is_(None),
            AgentLongTermMemory.session_id == session_id,
        )
        stmt = (
            select(AgentLongTermMemory)
            .where(
                AgentLongTermMemory.workspace_id == workspace_id,
                scope,
            )
            .order_by(desc(AgentLongTermMemory.created_at))
            .limit(cap)
        )
        if q:
            stmt = stmt.where(
                or_(
                    AgentLongTermMemory.content.ilike(pattern),
                    AgentLongTermMemory.key.ilike(pattern),
                )
            )
        rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            hits.append(
                MemoryHit(
                    content=row.content,
                    kind=row.kind,
                    source="long_term",
                    key=row.key,
                    memory_id=row.id,
                )
            )

        if len(hits) >= cap or not q:
            return hits[:cap]

        msg_cap = settings.agent_message_fallback_limit
        msg_stmt = (
            select(AgentMessage)
            .where(
                AgentMessage.session_id == session_id,
                AgentMessage.content.is_not(None),
                AgentMessage.content.ilike(pattern),
            )
            .order_by(desc(AgentMessage.seq))
            .limit(msg_cap)
        )
        if session_id is not None:
            for msg in (await session.execute(msg_stmt)).scalars().all():
                if len(hits) >= cap:
                    break
                text = (msg.content or "").strip()
                if not text:
                    continue
                hits.append(
                    MemoryHit(
                        content=text[:2000],
                        kind="message",
                        source="message",
                    )
                )
        return hits[:cap]

    async def upsert_fact(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        key: str | None,
        content: str,
        kind: str = "fact",
        tags: list[str] | None = None,
        source_run_id: uuid.UUID | None = None,
    ) -> AgentLongTermMemory:
        """Insert or update a fact row keyed by workspace + optional key."""

        if key:
            existing_stmt = select(AgentLongTermMemory).where(
                AgentLongTermMemory.workspace_id == workspace_id,
                AgentLongTermMemory.key == key,
                AgentLongTermMemory.kind == kind,
            )
            if session_id is not None:
                existing_stmt = existing_stmt.where(
                    AgentLongTermMemory.session_id == session_id
                )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing is not None:
                existing.content = content
                existing.tags = tags
                existing.source_run_id = source_run_id
                await session.flush()
                return existing

        row = AgentLongTermMemory(
            workspace_id=workspace_id,
            session_id=session_id,
            kind=kind,
            key=key,
            content=content,
            tags=tags,
            source_run_id=source_run_id,
        )
        session.add(row)
        await session.flush()
        return row

    async def insert_summary(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        content: str,
        source_run_id: uuid.UUID | None = None,
    ) -> AgentLongTermMemory:
        """Append an episode summary row."""

        row = AgentLongTermMemory(
            workspace_id=workspace_id,
            session_id=session_id,
            kind="summary",
            key=None,
            content=content,
            tags=None,
            source_run_id=source_run_id,
        )
        session.add(row)
        await session.flush()
        return row

    async def touch_session_summary(
        self,
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        summary_text: str,
    ) -> None:
        """Update rolling summary on ``agent_session``."""

        from app.agent.domain.db.models import AgentSession

        row = await session.get(AgentSession, session_id)
        if row is None:
            return
        row.summary_text = summary_text[:8000]
        row.updated_at = datetime.now(timezone.utc)
        await session.flush()
