"""Executor scheduling helpers: runnable steps and parallel policy."""

from __future__ import annotations

from app.agent.domain.plan import Plan, PlanStep
from app.config import settings

_SERIAL_ONLY_SKILLS = frozenset({"file", "ppt"})


def completed_step_ids(plan: Plan) -> set[str]:
    """Return step ids that finished (success, failed, or skipped)."""

    return {
        step.id
        for step in plan.steps
        if step.status in ("success", "failed", "skipped")
    }


def find_runnable_steps(plan: Plan) -> list[PlanStep]:
    """Steps whose dependencies are satisfied and status is pending."""

    done = completed_step_ids(plan)
    runnable: list[PlanStep] = []
    for step in plan.steps:
        if step.status != "pending":
            continue
        deps = step.depends_on or []
        if all(dep in done for dep in deps):
            runnable.append(step)
    return runnable


def select_steps_to_run(plan: Plan) -> list[PlanStep]:
    """Pick steps for this executor invocation (serial or parallel batch)."""

    runnable = find_runnable_steps(plan)
    if not runnable:
        return []

    if not settings.agent_parallel_steps_enabled or len(runnable) <= 1:
        return [runnable[0]]

    if any(step.skill_id in _SERIAL_ONLY_SKILLS for step in runnable):
        return [runnable[0]]

    independent = [s for s in runnable if not (s.depends_on or [])]
    if len(independent) >= 2:
        return independent
    return [runnable[0]]


def has_pending_runnable_steps(plan: Plan | None) -> bool:
    """True when at least one step can still run."""

    if plan is None or not plan.steps:
        return False
    return bool(find_runnable_steps(plan))
