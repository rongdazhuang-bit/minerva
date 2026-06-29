"""Relative-time detection and executor temporal anchor helpers."""

from __future__ import annotations

from typing import Any

from app.agent.infrastructure.datetime_tool import resolve_system_datetime

# Substring triggers; English matching is case-insensitive via lowered haystack.
_TEMPORAL_ANCHOR_PHRASES: tuple[str, ...] = (
    "今年",
    "去年",
    "前年",
    "本年度",
    "去年同期",
    "同比",
    "本季度",
    "上季度",
    "第一季度",
    "第二季度",
    "第三季度",
    "第四季度",
    "本月",
    "上月",
    "本周",
    "上周",
    "月初",
    "月末",
    "今天",
    "昨天",
    "前天",
    "明天",
    "q1",
    "q2",
    "q3",
    "q4",
    "this year",
    "last year",
    "ytd",
    "mtd",
    "yoy",
    "qoq",
    "same period last year",
)


def user_message_needs_temporal_anchor(text: str) -> bool:
    """Return True when the message contains relative-time phrases needing a date anchor."""

    haystack = (text or "").strip()
    if not haystack:
        return False
    lowered = haystack.lower()
    return any(
        phrase in lowered if phrase.isascii() else phrase in haystack
        for phrase in _TEMPORAL_ANCHOR_PHRASES
    )


def prefetch_system_datetime(*, timezone: str = "LOCAL") -> dict[str, Any]:
    """Synchronously prefetch server datetime for injection into sub-agent goals."""

    return resolve_system_datetime(timezone)


def format_temporal_anchor_prefix(payload: dict[str, Any]) -> str:
    """Format the prefetched datetime block for sub-agent consumption."""

    iso = payload.get("iso", "")
    tz = payload.get("timezone", "LOCAL")
    return (
        f"【系统当前时间】{iso}（{tz}）\n"
        "据此解析用户消息中的相对时间（今年/去年/本季度/去年同期等），禁止臆造年份。"
    )


def build_temporal_step_goal(base_goal: str, payload: dict[str, Any]) -> str:
    """Prepend temporal anchor instructions and prefetched time to the plan step goal."""

    anchor = format_temporal_anchor_prefix(payload)
    instruction = (
        "【时间锚定】上方已注入服务器当前时间，禁止调用 get_system_datetime；"
        "直接据此解析相对时间区间。"
    )
    body = (base_goal or "").strip()
    return f"{anchor}\n\n{instruction}\n\n{body}".strip()


def prepare_executor_temporal_context(
    *,
    user_message: str,
    step_goal: str,
    mcp_extra_tools: list[Any] | None,
) -> tuple[str, list[Any]]:
    """Return effective goal and extra tools (unchanged extras; prefetch only, no datetime tool)."""

    extras = list(mcp_extra_tools or [])
    if not user_message_needs_temporal_anchor(user_message):
        return step_goal, extras
    payload = prefetch_system_datetime(timezone="LOCAL")
    effective_goal = build_temporal_step_goal(step_goal, payload)
    return effective_goal, extras
