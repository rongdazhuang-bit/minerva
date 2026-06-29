"""Datetime skill tools (``register_tools`` + JSON ok contract)."""

from __future__ import annotations

from typing import Any

from app.agent.infrastructure.datetime_tool import get_system_datetime
from app.agent.infrastructure.skill_tool_context import SkillToolContext


def register_tools(_ctx: SkillToolContext) -> list[Any]:
    """Register datetime tools for on-demand skill loading."""

    return [get_system_datetime]
