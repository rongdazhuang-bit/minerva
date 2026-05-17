"""Load skills from ``skills/INDEX.md`` and per-skill ``SKILL.md`` / ``register_tools``."""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agent.infrastructure.skill_tool_context import SkillToolContext

log = logging.getLogger(__name__)

_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"
_INDEX_FILE = "INDEX.md"
_INDEX_ENTRY_RE = re.compile(r"^-\s*`([^`]+)`\s*[：:]\s*(.+?)\s*$")

_SECTION_WHEN_TO_USE = "## 何时使用"
_SECTION_PLANNER_ROUTING = "## Planner 路由"


@dataclass(frozen=True)
class IndexedSkill:
    """One row from ``skills/INDEX.md``."""

    id: str
    description: str


def skills_root() -> Path:
    """Return the root directory for built-in skill packages."""

    return _SKILLS_ROOT


def load_index_markdown() -> str:
    """Read ``skills/INDEX.md`` when present."""

    path = skills_root() / _INDEX_FILE
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def parse_index_skill_entries(index_text: str | None = None) -> list[IndexedSkill]:
    """Parse ``## 子技能列表`` bullets: ``- `id`：描述``."""

    text = index_text if index_text is not None else load_index_markdown()
    if not text:
        return _discover_skills_from_directories()
    entries: list[IndexedSkill] = []
    in_list = False
    for line in text.splitlines():
        stripped = line.strip()
        if "子技能列表" in stripped:
            in_list = True
            continue
        if in_list and stripped.startswith("## "):
            break
        if not in_list:
            continue
        match = _INDEX_ENTRY_RE.match(stripped)
        if match:
            sid = _normalize_skill_id(match.group(1))
            entries.append(IndexedSkill(id=sid, description=match.group(2).strip()))
    if entries:
        return entries
    return _discover_skills_from_directories()


def _discover_skills_from_directories() -> list[IndexedSkill]:
    """Fallback when INDEX.md is missing: subdirs with ``SKILL.md``, sorted by name."""

    root = skills_root()
    if not root.is_dir():
        return []
    found: list[IndexedSkill] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "SKILL.md").is_file():
            found.append(IndexedSkill(id=child.name, description=child.name))
    return found


@lru_cache(maxsize=1)
def list_indexed_skills() -> tuple[IndexedSkill, ...]:
    """Cached skill registry from INDEX.md (order = planner routing priority)."""

    return tuple(parse_index_skill_entries())


def list_indexed_skill_ids() -> list[str]:
    """Skill ids in INDEX order."""

    return [s.id for s in list_indexed_skills()]


def get_indexed_skill(skill_id: str) -> IndexedSkill | None:
    """Look up one skill row from ``skills/INDEX.md``."""

    sid = _normalize_skill_id(skill_id)
    for skill in list_indexed_skills():
        if skill.id == sid:
            return skill
    return None


def default_skill_id() -> str:
    """Default planner/executor skill when no trigger matches (prefer ``general``)."""

    ids = list_indexed_skill_ids()
    if "general" in ids:
        return "general"
    return ids[-1] if ids else "general"


def skill_id_field_description() -> str:
    """Build ``PlanStep.skill_id`` schema description from INDEX.md."""

    parts = [f"{s.id}={s.description}" for s in list_indexed_skills()]
    allowed = ", ".join(list_indexed_skill_ids())
    return f"要执行的 skill（仅可为 {allowed} 之一）：" + "；".join(parts)


def load_skill_markdown(skill_id: str) -> str:
    """Read ``skills/<id>/SKILL.md`` when present."""

    sid = _normalize_skill_id(skill_id)
    path = skills_root() / sid / "SKILL.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def extract_skill_when_to_use(skill_id: str) -> str:
    """Return the body of the ``## 何时使用`` section from SKILL.md (for planner routing)."""

    body = load_skill_markdown(skill_id)
    if not body:
        return ""
    return _section_body(body, _SECTION_WHEN_TO_USE).replace("\n", " ")


def load_tools_for_skill(skill_id: str, ctx: SkillToolContext) -> list[Any]:
    """Import ``skills.<id>.tools`` and call ``register_tools(ctx)``."""

    sid = _normalize_skill_id(skill_id)
    module_name = f"app.agent.skills.{sid}.tools"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        log.warning("skill tools module missing: %s", module_name)
        return []
    register = getattr(module, "register_tools", None)
    if register is None:
        return []
    try:
        tools = register(ctx)
    except Exception:
        log.exception("register_tools failed for skill=%s", sid)
        return []
    if not isinstance(tools, list):
        log.warning("register_tools for %s did not return a list", sid)
        return []
    return tools


def build_skill_system_prompt(skill_id: str) -> str:
    """Combine INDEX.md role line with ``SKILL.md`` for one sub-agent."""

    sid = _normalize_skill_id(skill_id)
    entry = get_indexed_skill(sid)
    base = (entry.description if entry else "").strip()
    skill_md = load_skill_markdown(sid)
    if skill_md:
        if base:
            return f"{base}\n\n## 技能说明\n{skill_md}"
        return skill_md
    if base:
        return base
    fallback = get_indexed_skill(default_skill_id())
    return fallback.description if fallback else ""


def build_skill_react_agent(
    model: BaseChatModel,
    skill_id: str,
    ctx: SkillToolContext,
    *,
    cache: dict[tuple[str, str], CompiledStateGraph] | None = None,
) -> CompiledStateGraph:
    """Compile a ReAct sub-agent with tools loaded on demand for one skill."""

    sid = _normalize_skill_id(skill_id)
    cache_key = (sid, str(ctx.workspace_id))
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    tools = load_tools_for_skill(sid, ctx)
    prompt = build_skill_system_prompt(sid)
    graph = create_react_agent(model, tools=tools, prompt=prompt)
    if cache is not None:
        cache[cache_key] = graph
    return graph


def _section_body(body: str, heading: str) -> str:
    """Return markdown section text under ``heading`` until the next ``## ``."""

    lines = body.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if line.strip().startswith(heading):
            start = i + 1
            break
    if start is None:
        return ""
    out: list[str] = []
    for line in lines[start:]:
        if line.strip().startswith("## "):
            break
        stripped = line.strip()
        if stripped:
            out.append(stripped)
    return "\n".join(out)


def extract_planner_route_triggers(skill_id: str) -> list[str]:
    """Parse bullet triggers under ``## Planner 路由`` in SKILL.md."""

    body = load_skill_markdown(skill_id)
    if not body:
        return []
    section = _section_body(body, _SECTION_PLANNER_ROUTING)
    triggers: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            triggers.append(stripped[2:].strip())
    return [t for t in triggers if t]


def match_skill_for_planner_message(user_message: str) -> str | None:
    """Pick skill_id when user text matches a SKILL.md ``Planner 路由`` trigger (substring)."""

    text = (user_message or "").strip()
    if not text:
        return None
    lowered = text.lower()
    for skill in list_indexed_skills():
        for trigger in extract_planner_route_triggers(skill.id):
            if trigger.lower() in lowered:
                return skill.id
    return None


def apply_planner_skill_match(plan: "Plan", user_message: str) -> "Plan":
    """Align single-step plans with SKILL.md ``Planner 路由`` triggers when matched."""

    from app.agent.domain.plan import Plan, PlanStep

    if not isinstance(plan, Plan) or not plan.steps:
        return plan
    matched = match_skill_for_planner_message(user_message)
    if matched is None:
        return plan
    if len(plan.steps) == 1:
        step = plan.steps[0]
        if step.skill_id != matched:
            plan.steps[0] = PlanStep(
                id=step.id,
                skill_id=matched,
                goal=step.goal or user_message,
                status=step.status,
                done_criteria=step.done_criteria,
            )
    return plan


def build_planner_skill_index() -> str:
    """Build planner-facing skill routing text from INDEX + each SKILL.md."""

    blocks: list[str] = []
    for skill in list_indexed_skills():
        when = extract_skill_when_to_use(skill.id)
        routes = extract_planner_route_triggers(skill.id)
        route_line = f"触发词：{'、'.join(routes)}" if routes else ""
        blocks.append(
            f"### {skill.id}（{skill.description}）\n{when}\n{route_line}".strip()
        )
    return "\n\n".join(blocks)


def build_planner_system_intro() -> str:
    """One-line allowed skill_id list for the planner system prompt."""

    return " | ".join(list_indexed_skill_ids())


def _normalize_skill_id(skill_id: str) -> str:
    """Normalize skill id to lowercase alphanumeric + underscore."""

    return (skill_id or "").strip().lower()
