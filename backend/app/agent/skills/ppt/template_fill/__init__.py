"""Template-fill engine: analyze source deck, plan, check, and apply."""

from app.agent.skills.ppt.template_fill.analyze import analyze_template
from app.agent.skills.ppt.template_fill.apply import apply_fill_plan
from app.agent.skills.ppt.template_fill.check_plan import check_fill_plan
from app.agent.skills.ppt.template_fill.plan_builder import outline_to_fill_plan

__all__ = [
    "analyze_template",
    "apply_fill_plan",
    "check_fill_plan",
    "outline_to_fill_plan",
]
