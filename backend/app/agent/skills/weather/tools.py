"""Weather skill tools (``register_tools`` + JSON ok contract)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.agent.infrastructure.amap_client import get_weather
from app.agent.infrastructure.skill_tool_context import SkillToolContext


def register_tools(_ctx: SkillToolContext) -> list[Any]:
    """Register Amap weather query tools."""

    @tool
    async def get_weather_info(city_adcode: str, extensions: str = "all") -> str:
        """按城市 adcode 查询天气；extensions 默认 all（实况+预报）。"""

        result = await get_weather(city_adcode=city_adcode, extensions=extensions)
        return json.dumps(result, ensure_ascii=False)

    return [get_weather_info]
