"""IP location skill tools (``register_tools`` + JSON ok contract)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.agent.infrastructure.amap_client import lookup_ip
from app.agent.infrastructure.skill_tool_context import SkillToolContext


def register_tools(_ctx: SkillToolContext) -> list[Any]:
    """Register Amap IP geolocation tools."""

    @tool
    async def lookup_ip_location(ip: str | None = None) -> str:
        """根据 IP 地址查询国内所在省市与 adcode；ip 为空时使用请求方 IP。"""

        result = await lookup_ip(ip=ip)
        return json.dumps(result, ensure_ascii=False)

    return [lookup_ip_location]
