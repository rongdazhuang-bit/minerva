"""General skill: no tools (``register_tools``)."""

from __future__ import annotations

from typing import Any

from app.agent.infrastructure.skill_tool_context import SkillToolContext


def register_tools(_ctx: SkillToolContext) -> list[Any]:
    """General dialogue does not expose tools; the model answers directly."""

    return []
