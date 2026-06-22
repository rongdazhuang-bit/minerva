"""Deterministic request routing for agent graph entry paths."""

from __future__ import annotations

import re
from typing import Literal

from app.agent.domain.plan import Plan, PlanStep
from app.agent.infrastructure.skill_loader import (
    default_skill_id,
    get_indexed_skill,
    list_indexed_skills,
    match_skill_for_planner_message,
    plan_from_preferred_skill,
    extract_planner_route_triggers,
)
from app.config import settings

RouteKind = Literal["direct_chat", "single_skill", "full_pipeline"]

_MULTI_STEP_RE = re.compile(
    r"(然后|接着|之后再|之后|第一步|第二步|先.+再|同时.+并且)",
)

_DEFAULT_TOOL_KEYWORDS: tuple[str, ...] = (
    "文件",
    "目录",
    "天气",
    "ppt",
    "演示",
    "幻灯片",
    "读取",
    "写入",
    "下载",
    "上传",
    "查询",
    "定位",
    "ip",
)

_DEFAULT_RECALL_KEYWORDS: tuple[str, ...] = (
    "回忆",
    "上次",
    "记住",
    "之前说过",
    "还记得",
    "历史记录",
)


def recall_keywords() -> tuple[str, ...]:
    """Configured keywords that imply long-term memory is needed."""

    raw = (settings.agent_memory_recall_keywords or "").strip()
    if not raw:
        return _DEFAULT_RECALL_KEYWORDS
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(parts) if parts else _DEFAULT_RECALL_KEYWORDS


def has_recall_keywords(user_message: str) -> bool:
    """Return True when the user message asks to recall prior context."""

    text = (user_message or "").strip().lower()
    if not text:
        return False
    return any(kw.lower() in text for kw in recall_keywords())


def has_tool_oriented_keywords(user_message: str) -> bool:
    """Return True when the message likely needs a non-general skill."""

    text = (user_message or "").strip().lower()
    if not text:
        return False
    return any(kw.lower() in text for kw in _DEFAULT_TOOL_KEYWORDS)


def looks_multi_step(user_message: str) -> bool:
    """Heuristic for compound tasks that need full planning."""

    text = (user_message or "").strip()
    if not text:
        return False
    if _MULTI_STEP_RE.search(text):
        return True
    if text.count("，") >= 2 and has_tool_oriented_keywords(text):
        return True
    return False


def match_all_skills_for_planner_message(user_message: str) -> list[str]:
    """Return skill ids whose Planner 路由 triggers match the message (INDEX order)."""

    text = (user_message or "").strip()
    if not text:
        return []
    lowered = text.lower()
    matched: list[str] = []
    for skill in list_indexed_skills():
        for trigger in extract_planner_route_triggers(skill.id):
            if trigger.lower() in lowered:
                matched.append(skill.id)
                break
    return matched


def is_simple_chat_message(user_message: str, *, max_chars: int) -> bool:
    """Heuristic for greetings and short chit-chat suitable for direct_chat."""

    text = (user_message or "").strip()
    if not text or len(text) > max_chars:
        return False
    if has_tool_oriented_keywords(text):
        return False
    if looks_multi_step(text):
        return False
    if has_recall_keywords(text):
        return False
    return True


def classify_route(
    user_message: str,
    preferred_skills: list[str] | None,
    *,
    router_enabled: bool | None = None,
    simple_max_chars: int | None = None,
) -> RouteKind:
    """Pick graph entry path: direct_chat, single_skill, or full_pipeline."""

    enabled = settings.agent_router_enabled if router_enabled is None else router_enabled
    if not enabled:
        return "full_pipeline"

    pref = list(preferred_skills or [])
    text = (user_message or "").strip()

    if len(pref) == 1 and get_indexed_skill(pref[0]) is not None:
        return "single_skill"

    if looks_multi_step(text):
        return "full_pipeline"

    matched_skills = match_all_skills_for_planner_message(text)
    non_general = [s for s in matched_skills if s != default_skill_id()]
    if len(non_general) == 1:
        return "single_skill"
    if len(non_general) > 1:
        return "full_pipeline"

    if not pref and is_simple_chat_message(
        text,
        max_chars=simple_max_chars or settings.agent_router_simple_max_chars,
    ):
        single_match = match_skill_for_planner_message(text)
        if single_match is None or single_match == default_skill_id():
            return "direct_chat"

    return "full_pipeline"


def plan_for_single_skill_route(
    user_message: str,
    preferred_skills: list[str] | None,
) -> Plan | None:
    """Build a one-step plan without Planner LLM for single_skill routing."""

    pref = list(preferred_skills or [])
    text = (user_message or "").strip()
    from_pref = plan_from_preferred_skill(pref, text)
    if from_pref is not None:
        return from_pref

    matched = match_all_skills_for_planner_message(text)
    non_general = [s for s in matched if s != default_skill_id()]
    skill_id = non_general[0] if len(non_general) == 1 else match_skill_for_planner_message(text)
    if skill_id is None:
        return None
    goal = text or skill_id
    return Plan(steps=[PlanStep(id="s1", skill_id=skill_id, goal=goal)])
