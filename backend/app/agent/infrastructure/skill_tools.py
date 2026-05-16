"""Load per-skill ``tools.py`` modules and populate a ``ToolRegistry``."""

from __future__ import annotations

import importlib.util
import logging
import re

from app.agent.infrastructure.skill_loader import skills_root
from app.agent.infrastructure.tool_registry import ToolRegistry
from app.exceptions import AppError

log = logging.getLogger(__name__)

_SKILL_ID_RE = re.compile(r"^[a-z0-9_]+$")


def load_tools_for_skills(skill_ids: list[str]) -> ToolRegistry:
    """Import each skill's ``tools.py`` and call ``register(registry)``."""

    registry = ToolRegistry()
    root = skills_root()
    for raw in skill_ids:
        sid = raw.strip().lower()
        if not sid or not _SKILL_ID_RE.fullmatch(sid):
            continue
        tools_path = root / sid / "tools.py"
        if not tools_path.is_file():
            continue
        mod_name = f"agent_skill_{sid}_tools"
        spec = importlib.util.spec_from_file_location(mod_name, tools_path)
        if spec is None or spec.loader is None:
            log.warning("skill tools spec failed skill_id=%s", sid)
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            log.warning("skill tools import failed skill_id=%s err=%s", sid, e)
            continue
        register_fn = getattr(module, "register", None)
        if not callable(register_fn):
            log.warning("skill tools missing register() skill_id=%s", sid)
            continue
        before = set(registry.tool_names())
        try:
            register_fn(registry)
        except AppError:
            raise
        except Exception as e:
            log.warning("skill tools register failed skill_id=%s err=%s", sid, e)
            continue
        after = set(registry.tool_names())
        added = after - before
        if len(after) - len(before) != len(added):
            raise AppError(
                "agent.skill.tool_name_conflict",
                f"duplicate tool name while loading skill {sid}",
            )
    return registry
