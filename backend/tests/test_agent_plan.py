"""Tests for agent Plan models."""

from app.agent.domain.plan import Plan, PlanStep


def test_plan_step_capability_normalized() -> None:
    """Capability names are lowercased on validation."""

    step = PlanStep(id="1", capability="FILE", goal="list files")
    assert step.capability == "file"


def test_plan_from_json_steps() -> None:
    """Plan validates a JSON-shaped steps list."""

    raw = {
        "steps": [
            {"id": "s1", "capability": "general", "goal": "greet", "status": "pending"}
        ]
    }
    plan = Plan.model_validate(raw)
    assert len(plan.steps) == 1
    assert plan.steps[0].capability == "general"
