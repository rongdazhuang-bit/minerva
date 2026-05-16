"""Executable tools for the ``system_datetime`` agent skill."""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone as dt_timezone

from app.agent.infrastructure.tool_registry import ToolRegistry


async def _get_system_datetime(*, timezone: str = "UTC") -> str:
    """Return current server time as JSON (``iso``, ``timezone``, ``unix``)."""

    tz = (timezone or "UTC").strip().upper()
    if tz == "LOCAL":
        now = datetime.now().astimezone()
        tz_label = "local"
    else:
        now = datetime.now(dt_timezone.utc)
        tz_label = "UTC"
    iso = now.isoformat().replace("+00:00", "Z") if tz_label == "UTC" else now.isoformat()
    payload = {"iso": iso, "timezone": tz_label, "unix": int(now.timestamp())}
    return json.dumps(payload, ensure_ascii=False)


def register(registry: ToolRegistry) -> None:
    """Register ``get_system_datetime`` on the shared registry."""

    registry.register(
        "get_system_datetime",
        _get_system_datetime,
        description="返回服务器当前日期时间（ISO-8601）。",
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "enum": ["UTC", "local"],
                    "description": "时区：UTC 或服务器本地。",
                }
            },
        },
    )
