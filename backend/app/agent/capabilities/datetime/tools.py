"""LangChain tools for datetime capability."""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone as dt_timezone

from langchain_core.tools import tool


@tool
def get_system_datetime(timezone: str = "UTC") -> str:
    """返回服务器当前日期时间（ISO-8601 JSON，含 iso、timezone、unix）。"""

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
