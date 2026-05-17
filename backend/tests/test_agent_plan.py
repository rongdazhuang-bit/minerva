"""Tests for planner Plan / PlanStep models."""

from app.agent.domain.plan import Plan, PlanStep


def test_plan_step_skill_id_normalized() -> None:
    """Skill ids are lowercased on validation."""

    step = PlanStep(id="1", skill_id="FILE", goal="list files")
    assert step.skill_id == "file"


def test_plan_step_accepts_legacy_capability_alias() -> None:
    """Persisted plans with ``capability`` still deserialize."""

    step = PlanStep.model_validate({"id": "1", "capability": "file", "goal": "x"})
    assert step.skill_id == "file"


def test_plan_from_json() -> None:
    """Plan parses a list of steps from structured output shape."""

    plan = Plan.model_validate(
        {
            "steps": [
                {"id": "s1", "skill_id": "general", "goal": "greet", "status": "pending"}
            ]
        }
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].skill_id == "general"
