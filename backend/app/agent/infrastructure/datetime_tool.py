"""Shared system datetime resolution and LangChain tool for agent skills."""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any

from langchain_core.tools import tool


def resolve_system_datetime(timezone: str = "UTC") -> dict[str, Any]:
    """Return current server time as a dict (ok, iso, timezone, unix)."""

    tz = (timezone or "UTC").strip().upper()
    if tz == "LOCAL":
        now = datetime.now().astimezone()
        tz_label = "local"
    else:
        now = datetime.now(dt_timezone.utc)
        tz_label = "UTC"
    iso = now.isoformat().replace("+00:00", "Z") if tz_label == "UTC" else now.isoformat()
    return {
        "ok": True,
        "iso": iso,
        "timezone": tz_label,
        "unix": int(now.timestamp()),
    }


@tool
def get_system_datetime(timezone: str = "UTC") -> str:
    """返回服务器当前日期时间（JSON：ok, iso, timezone, unix）。"""

    return json.dumps(resolve_system_datetime(timezone), ensure_ascii=False)
