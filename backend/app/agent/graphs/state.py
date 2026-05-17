"""LangGraph state for the main Plan-and-Execute agent."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from app.agent.domain.plan import Plan
from app.agent.infrastructure.memory_store import MemoryHit


class StepResult(TypedDict, total=False):
    """Output from one executor step."""

    step_id: str
    capability: str
    output: str


class AgentGraphState(TypedDict, total=False):
    """Shared state for the main agent graph."""

    session_id: uuid.UUID
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    model_id: uuid.UUID
    user_message: str
    preferred_capabilities: list[str]
    plan: Plan | None
    plan_id: uuid.UUID | None
    current_step_index: int
    retrieved_memories: list[MemoryHit]
    subagent_results: list[StepResult]
    final_answer: str | None
    error: str | None
