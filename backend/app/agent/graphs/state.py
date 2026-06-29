"""LangGraph state for the main Plan-and-Execute agent graph."""

from __future__ import annotations

import uuid
from typing import TypedDict

from app.agent.domain.plan import Plan
from app.agent.memory.hits import MemoryHit


class StepResult(TypedDict, total=False):
    """Output from one executor step."""

    step_id: str
    skill_id: str
    output: str
    tool_call_count: int
    last_ai_had_tool_calls: bool


class AgentGraphState(TypedDict, total=False):
    """Shared state for the main agent graph."""

    session_id: uuid.UUID
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    model_id: uuid.UUID
    user_message: str
    preferred_skills: list[str]
    plan: Plan | None
    plan_id: uuid.UUID | None
    current_step_index: int
    retrieved_memories: list[MemoryHit]
    memory_context: str
    subagent_results: list[StepResult]
    final_answer: str | None
    error: str | None
