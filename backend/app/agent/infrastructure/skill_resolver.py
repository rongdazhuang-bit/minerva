"""Resolve which skill packs are active for a single agent run."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

SKILL_KEYWORDS: dict[str, list[str]] = {
    "system_datetime": [
        "时间",
        "几点",
        "日期",
        "今天",
        "现在",
        "星期",
        "time",
        "date",
        "datetime",
    ],
    "file": [
        "文件",
        "目录",
        "文件夹",
        "读取",
        "写入",
        "保存",
        "删除",
        "创建",
        "重命名",
        "移动",
        "列出",
        "list",
        "read",
        "write",
        "mkdir",
        "delete",
        "move",
        "file",
        "folder",
        "directory",
    ],
}


def match_skills_from_message(user_message: str, index_skill_ids: list[str]) -> list[str]:
    """Heuristic keyword match against registered index ids."""

    msg = user_message or ""
    msg_lower = msg.lower()
    allowed = set(index_skill_ids)
    matched: list[str] = []
    for sid, keywords in SKILL_KEYWORDS.items():
        if sid not in allowed:
            continue
        if any(kw in msg or kw.lower() in msg_lower for kw in keywords):
            matched.append(sid)
    return matched


def resolve_effective_skill_ids(
    *,
    user_message: str,
    requested_skill_ids: list[str],
    index_skill_ids: list[str],
) -> list[str]:
    """Explicit ``requested_skill_ids`` wins; otherwise auto-match from message."""

    allowed = set(index_skill_ids)
    explicit = [s.strip().lower() for s in requested_skill_ids if s and s.strip()]
    if explicit:
        out: list[str] = []
        for sid in explicit:
            if sid not in allowed:
                log.warning("skill id not in index, skipping: %s", sid)
                continue
            out.append(sid)
        return out
    return match_skills_from_message(user_message, index_skill_ids)
