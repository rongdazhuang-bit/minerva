"""Decide whether memory.retrieve should run for the current graph state."""

from __future__ import annotations

from app.agent.graphs.state import AgentGraphState
from app.agent.infrastructure.request_router import has_recall_keywords
from app.config import settings


async def should_skip_memory_retrieve(
    state: AgentGraphState,
    *,
    memory_count: int | None = None,
) -> bool:
    """Return True when long-term memory retrieval can be skipped this turn."""

    if state.get("skip_memory"):
        return True
    if state.get("route_kind") == "direct_chat":
        return True
    if settings.agent_memory_backend != "sql":
        return False
    if not settings.agent_memory_retrieve_skip_when_empty:
        return False
    if has_recall_keywords(state.get("user_message", "")):
        return False
    if memory_count is None:
        return False
    return memory_count <= 0
