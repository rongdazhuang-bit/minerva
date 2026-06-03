"""mem0-backed memory retrieve strategy."""

from __future__ import annotations

from app.core.log import get_logger
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory.hits import MemoryHit
from app.agent.memory.mem0.client import get_mem0_memory, mem0_entity_filters
from app.agent.memory.mem0.profile_runtime import build_runtime_session_profile
from app.agent.memory.profile import service as profile_service
from app.agent.memory.sql.retrieve import format_memory_hits_for_planner
from app.agent.memory.mem0.embedder_config import mem0_embedder_endpoint_summary
from app.config import settings

log = get_logger(__name__)


def _search_hits_sync(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID | None,
    query_text: str,
    limit: int,
) -> list[MemoryHit]:
    """Blocking mem0 search mapped to ``MemoryHit``."""

    memory = get_mem0_memory()
    result = memory.search(
        query_text or "",
        top_k=limit,
        filters=mem0_entity_filters(
            workspace_id=workspace_id,
            session_id=session_id,
        ),
        rerank=settings.agent_memory_mem0_rerank_enabled,
    )
    hits: list[MemoryHit] = []
    for item in result.get("results") or []:
        text = (item.get("memory") or item.get("text") or "").strip()
        if not text:
            continue
        hits.append(
            MemoryHit(
                content=text,
                kind="mem0",
                source="mem0",
                memory_id=item.get("id"),
                score=float(item["score"]) if item.get("score") is not None else None,
            )
        )
    return hits


class Mem0MemoryRetrieveStrategy:
    """Retrieve via mem0 vector + graph store."""

    async def retrieve(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        query_text: str,
        limit: int | None = None,
    ) -> list[MemoryHit]:
        """Search mem0; return empty list on failure."""

        _ = session
        cap = limit if limit is not None else settings.agent_memory_retrieve_limit
        if session_id is None:
            return []
        try:
            return await asyncio.to_thread(
                _search_hits_sync,
                workspace_id=workspace_id,
                session_id=session_id,
                query_text=query_text,
                limit=cap,
            )
        except Exception as e:
            log.warning(
                "mem0 retrieve failed ({}): {}",
                mem0_embedder_endpoint_summary(),
                e,
                exc_info=True,
            )
            return []

    async def build_planner_context(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID | None,
        query_text: str,
        hits: list[MemoryHit],
    ) -> str:
        """Layer persistent profiles, runtime session profile, and hits."""

        parts: list[str] = []
        workspace_text, session_profile_text = await profile_service.get_profile_layers_text(
            session,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if workspace_text:
            parts.append("## 工作区画像\n" + workspace_text[:2000])
        if session_profile_text:
            parts.append("## 会话画像\n" + session_profile_text[:2000])
        if session_id is not None:
            runtime = await build_runtime_session_profile(
                workspace_id=workspace_id,
                session_id=session_id,
                query_text=query_text,
            )
            if runtime:
                parts.append("## 本轮上下文\n" + runtime[:2000])
        hit_block = format_memory_hits_for_planner(hits)
        if hit_block:
            parts.append(hit_block)
        return "\n\n".join(parts)
