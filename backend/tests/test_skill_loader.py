"""Tests for agent skill loading (SKILL.md + register_tools)."""

from __future__ import annotations

import json
import uuid

from app.agent.domain.plan import Plan, PlanStep
from app.agent.infrastructure.skill_loader import (
    apply_planner_skill_match,
    build_planner_skill_index,
    build_skill_system_prompt,
    extract_skill_when_to_use,
    list_indexed_skill_ids,
    load_index_markdown,
    load_skill_markdown,
    load_tools_for_skill,
    match_skill_for_planner_message,
    parse_index_skill_entries,
)
from app.agent.infrastructure.skill_tool_context import SkillToolContext


def test_index_lists_builtin_skills_in_order() -> None:
    """INDEX.md defines skill ids and planner routing priority."""

    ids = list_indexed_skill_ids()
    assert ids == ["datetime", "file", "general"]
    entries = parse_index_skill_entries(load_index_markdown())
    assert entries[0].id == "datetime"
    assert "get_system_datetime" in entries[0].description


def test_load_skill_markdown_file() -> None:
    """File skill ships SKILL.md with tool contract hints."""

    text = load_skill_markdown("file")
    assert "list_dir" in text
    assert '"ok": true' in text or "ok" in text.lower()


def test_register_tools_file_and_datetime() -> None:
    """On-demand loaders expose file and datetime tools via register_tools."""

    ctx = SkillToolContext(workspace_id=uuid.uuid4())
    file_tools = load_tools_for_skill("file", ctx)
    assert len(file_tools) == 6
    file_names = {t.name for t in file_tools}
    assert "read_file" in file_names

    dt_tools = load_tools_for_skill("datetime", ctx)
    assert len(dt_tools) == 1
    assert dt_tools[0].name == "get_system_datetime"

    general_tools = load_tools_for_skill("general", ctx)
    assert general_tools == []


def test_get_system_datetime_ok_json() -> None:
    """Datetime tool follows skills JSON success envelope."""

    ctx = SkillToolContext(workspace_id=uuid.uuid4())
    tools = load_tools_for_skill("datetime", ctx)
    raw = tools[0].invoke({"timezone": "UTC"})
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert "iso" in payload


def test_build_skill_system_prompt_includes_skill() -> None:
    """System prompt merges INDEX role line with SKILL.md body."""

    prompt = build_skill_system_prompt("file")
    assert "工作区文件助手" in prompt
    assert "技能说明" in prompt
    assert "list_dir" in prompt


def test_extract_skill_when_to_use_datetime() -> None:
    """何时使用 section mentions datetime skill_id for planner."""

    when = extract_skill_when_to_use("datetime")
    assert "skill_id=datetime" in when
    assert "general" in when


def test_build_planner_skill_index_includes_when_to_use() -> None:
    """Planner index embeds per-skill 何时使用 sections."""

    index = build_planner_skill_index()
    assert "### datetime（" in index
    assert "现在几点" in index
    assert "### general" in index


def test_match_skill_for_planner_message_datetime() -> None:
    """Planner 路由 triggers from SKILL.md match time questions."""

    assert match_skill_for_planner_message("现在几点") == "datetime"


def test_apply_planner_skill_match_overrides_general() -> None:
    """SKILL.md routing corrects LLM plan that wrongly picked general."""

    plan = Plan(steps=[PlanStep(id="s1", skill_id="general", goal="现在几点")])
    fixed = apply_planner_skill_match(plan, "现在几点")
    assert fixed.steps[0].skill_id == "datetime"


def test_match_skill_for_planner_message_file() -> None:
    """File SKILL.md Planner 路由 matches directory listing requests."""

    assert match_skill_for_planner_message("列出当前目录文件") == "file"
    assert match_skill_for_planner_message("读取 readme.md") == "file"


def test_apply_planner_skill_match_file_listing() -> None:
    """Listing sandbox files must route to file, not general."""

    plan = Plan(steps=[PlanStep(id="s1", skill_id="general", goal="列出当前目录文件")])
    fixed = apply_planner_skill_match(plan, "列出当前目录文件")
    assert fixed.steps[0].skill_id == "file"
