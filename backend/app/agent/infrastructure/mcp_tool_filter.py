"""Filter workspace MCP LangChain tools per skill whitelist rules."""

from __future__ import annotations

from typing import Any

from app.agent.infrastructure.skill_loader import (
    default_skill_id,
    load_skill_markdown,
    _section_body,
)

_SECTION_MCP_TOOLS = "## MCP 工具"


def extract_mcp_tool_rules(skill_id: str) -> list[str]:
    """Parse bullet lines under ``## MCP 工具`` in SKILL.md (prefix or full tool name)."""

    body = load_skill_markdown(skill_id)
    if not body:
        return []
    section = _section_body(body, _SECTION_MCP_TOOLS)
    rules: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            rule = stripped[2:].strip()
            if rule:
                rules.append(rule)
    return rules


def _tool_name(tool: Any) -> str | None:
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) and name else None


def _matches_rule(tool_name: str, rule: str) -> bool:
    rule = rule.strip()
    if not rule:
        return False
    if rule.endswith("*"):
        return tool_name.startswith(rule[:-1])
    return tool_name == rule or tool_name.startswith(f"{rule}_") or tool_name.startswith(rule)


def filter_mcp_tools_for_skill(skill_id: str, all_tools: list[Any]) -> list[Any]:
    """Return MCP tools visible to one skill (general gets all; others use SKILL.md whitelist)."""

    sid = (skill_id or "").strip().lower()
    if sid == default_skill_id():
        return list(all_tools or [])

    rules = extract_mcp_tool_rules(sid)
    if not rules:
        return []

    selected: list[Any] = []
    seen: set[str] = set()
    for tool in all_tools or []:
        name = _tool_name(tool)
        if not name or name in seen:
            continue
        if any(_matches_rule(name, rule) for rule in rules):
            selected.append(tool)
            seen.add(name)
    return selected
