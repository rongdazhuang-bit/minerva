"""Heuristic intent detection for planner fast-path routing."""

from __future__ import annotations

import re

# 短句日期/时间问询：避免依赖 LLM structured output 误选 general。
_DATETIME_QUERY_RE = re.compile(
    r"(?:"
    r"今天(?:是)?几号|今日(?:是)?几号|"
    r"现在几点|几点了|几时了|当前时间|现在时间|"
    r"今天星期几|今日星期几|星期几|周几|"
    r"什么日期|哪天|几月几号|"
    r"what(?:'s| is) (?:the )?date|what time is it|current (?:date|time)"
    r")",
    re.IGNORECASE,
)


def detect_datetime_intent(text: str) -> bool:
    """Return True when the user message is primarily asking for current date/time."""

    t = (text or "").strip()
    if not t or len(t) > 240:
        return False
    return _DATETIME_QUERY_RE.search(t) is not None
