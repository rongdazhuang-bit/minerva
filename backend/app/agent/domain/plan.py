"""Structured plan models for Plan-and-Execute agent runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

PlanStepStatus = Literal["pending", "running", "success", "failed", "skipped"]
CapabilityName = Literal["general", "file", "datetime"]


class PlanStep(BaseModel):
    """One executable step routed to a sub-agent capability."""

    id: str
    capability: CapabilityName
    goal: str
    status: PlanStepStatus = "pending"
    done_criteria: str | None = None

    @field_validator("capability", mode="before")
    @classmethod
    def _norm_capability(cls, v: object) -> str:
        """Normalize capability id to lowercase."""

        return str(v).strip().lower()


class Plan(BaseModel):
    """Planner output consumed by the executor node."""

    steps: list[PlanStep] = Field(default_factory=list)
