"""Structured plan models for Plan-and-Execute agent runs."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.agent.infrastructure.skill_loader import (
    default_skill_id,
    list_indexed_skill_ids,
    skill_id_field_description,
)

PlanStepStatus = Literal["pending", "running", "success", "failed", "skipped"]


class PlanStep(BaseModel):
    """One executable step routed to a sub-agent skill."""

    id: str = Field(description="步骤唯一 id，如 s1。")
    skill_id: str = Field(
        description=skill_id_field_description(),
        validation_alias=AliasChoices("skill_id", "capability"),
    )
    goal: str = Field(description="该步要完成的用户子目标，一句中文。")
    status: PlanStepStatus = "pending"
    done_criteria: str | None = None

    @field_validator("skill_id", mode="before")
    @classmethod
    def _norm_skill_id(cls, v: object) -> str:
        """Normalize skill id to lowercase."""

        return str(v).strip().lower()

    @field_validator("skill_id")
    @classmethod
    def _validate_skill_id_registered(cls, v: str) -> str:
        """Ensure skill_id is listed in ``skills/INDEX.json``."""

        allowed = list_indexed_skill_ids()
        if allowed and v not in allowed:
            raise ValueError(f"skill_id must be one of {allowed}, got {v!r}")
        return v


class Plan(BaseModel):
    """Planner output consumed by the executor node."""

    steps: list[PlanStep] = Field(
        default_factory=list,
        description="有序执行步骤；简单问题通常仅 1 步。",
    )


def plan_fallback_skill_id(user_message: str) -> str:
    """Pick fallback skill when planner structured output fails."""

    from app.agent.infrastructure.skill_loader import match_skill_for_planner_message

    return match_skill_for_planner_message(user_message) or default_skill_id()
