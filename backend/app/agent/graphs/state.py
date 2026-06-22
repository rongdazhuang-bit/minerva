"""LangGraph state for the main Plan-and-Execute agent graph."""

from __future__ import annotations

import uuid
from typing import Literal, TypedDict

from app.agent.domain.plan import Plan

RouteKind = Literal["direct_chat", "single_skill", "full_pipeline"]
from app.agent.memory.hits import MemoryHit


class StepResult(TypedDict, total=False):
    """Output from one executor step."""

    step_id: str
    skill_id: str
    output: str


class AgentGraphState(TypedDict, total=False):
    """Shared state for the main agent graph."""

    session_id: uuid.UUID
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    model_id: uuid.UUID
    user_message: str
    preferred_skills: list[str]
    route_kind: RouteKind | None
    skip_memory: bool
    plan: Plan | None
    plan_id: uuid.UUID | None
    current_step_index: int
    retrieved_memories: list[MemoryHit]
    memory_context: str
    subagent_results: list[StepResult]
    final_answer: str | None
    error: str | None
    abort_run: bool
    replan_requested: bool
    replan_attempt: int
