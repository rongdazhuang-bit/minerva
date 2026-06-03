"""Runtime session profile text from mem0 search (not persisted)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.agent.memory.mem0.client import get_mem0_memory
from app.config import settings

log = logging.getLogger(__name__)


def _search_sync(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    query_text: str,
    limit: int,
) -> list[str]:
    """Blocking mem0 search returning memory text lines."""

    memory = get_mem0_memory()
    result = memory.search(
        query_text or "user context",
        user_id=str(workspace_id),
        run_id=str(session_id),
        limit=limit,
        rerank=True,
    )
    lines: list[str] = []
    for item in result.get("results") or []:
        text = (item.get("memory") or item.get("text") or "").strip()
        if text:
            lines.append(text)
    return lines


async def build_runtime_session_profile(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    query_text: str,
) -> str:
    """Build ephemeral session profile from mem0 search (optional LLM synthesis)."""

    cap = min(10, settings.agent_memory_retrieve_limit)
    try:
        lines = await asyncio.to_thread(
            _search_sync,
            workspace_id=workspace_id,
            session_id=session_id,
            query_text=query_text,
            limit=cap,
        )
    except Exception:
        log.warning("mem0 runtime profile search failed", exc_info=True)
        return ""

    if not lines:
        return ""

    if not settings.agent_memory_profile_llm_enabled:
        return "\n".join(f"- {line[:400]}" for line in lines[:cap])

    # Optional LLM synthesis uses mem0-configured LLM via mem0 client only.
    # YAGNI: concatenate search hits when LLM flag is off (default).
    return "\n".join(f"- {line[:400]}" for line in lines[:cap])
