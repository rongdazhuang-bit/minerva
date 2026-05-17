"""Format deterministic datetime tool output into user-facing Chinese."""

from __future__ import annotations

import json
import re
from datetime import datetime

_WEEKDAY_ZH = ("一", "二", "三", "四", "五", "六", "日")

_TIME_HINT_RE = re.compile(r"几点|几时|时间|几点了|current time|what time", re.IGNORECASE)
_DATE_HINT_RE = re.compile(
    r"几号|哪天|日期|星期几|周几|几月几号|what(?:'s| is) (?:the )?date|current date",
    re.IGNORECASE,
)


def format_datetime_answer(tool_json: str, user_text: str) -> str:
    """Turn ``get_system_datetime`` JSON into a concise Chinese reply."""

    payload = json.loads(tool_json)
    iso = str(payload.get("iso") or "")
    tz_label = str(payload.get("timezone") or "UTC")
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    weekday = _WEEKDAY_ZH[dt.weekday()]
    date_part = f"{dt.year}年{dt.month}月{dt.day}日"
    time_part = dt.strftime("%H:%M:%S")
    tz_suffix = "（本地时区）" if tz_label == "local" else "（UTC）"

    question = user_text or ""
    if _TIME_HINT_RE.search(question) and not _DATE_HINT_RE.search(question):
        return f"当前服务器时间为 {time_part}{tz_suffix}。"
    if _DATE_HINT_RE.search(question) and not _TIME_HINT_RE.search(question):
        return f"今天是{date_part}，星期{weekday}。"
    return f"今天是{date_part}，星期{weekday}；当前服务器时间为 {time_part}{tz_suffix}。"
