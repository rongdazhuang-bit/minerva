"""District search skill tools (``register_tools`` + JSON ok contract)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.agent.infrastructure.amap_client import search_district
from app.agent.infrastructure.skill_tool_context import SkillToolContext


def register_tools(_ctx: SkillToolContext) -> list[Any]:
    """Register Amap administrative district search tools."""

    @tool
    async def search_district_tool(keywords: str, subdistrict: int = 0) -> str:
        """按行政区名称或 adcode 查询区划信息，返回 districts 列表。"""

        result = await search_district(keywords=keywords, subdistrict=subdistrict)
        return json.dumps(result, ensure_ascii=False)

    return [search_district_tool]
