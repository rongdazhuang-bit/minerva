"""Tests for Amap agent skills and skill_loader dependencies."""

from __future__ import annotations

import uuid

from app.agent.infrastructure.skill_loader import load_tools_for_skill
from app.agent.infrastructure.skill_tool_context import SkillToolContext


def test_weather_skill_loads_dependency_tools() -> None:
    """Loading weather also exposes ip and district tools."""

    ctx = SkillToolContext(workspace_id=uuid.uuid4())
    tools = load_tools_for_skill("weather", ctx)
    names = sorted(getattr(tool, "name", "") for tool in tools)
    assert names == ["get_weather_info", "lookup_ip_location", "search_district_tool"]


def test_ip_location_skill_loads_single_tool() -> None:
    """ip_location skill exposes only its own tool."""

    ctx = SkillToolContext(workspace_id=uuid.uuid4())
    tools = load_tools_for_skill("ip_location", ctx)
    names = [getattr(tool, "name", "") for tool in tools]
    assert names == ["lookup_ip_location"]


def test_district_skill_loads_single_tool() -> None:
    """district skill exposes only its own tool."""

    ctx = SkillToolContext(workspace_id=uuid.uuid4())
    tools = load_tools_for_skill("district", ctx)
    names = [getattr(tool, "name", "") for tool in tools]
    assert names == ["search_district_tool"]
