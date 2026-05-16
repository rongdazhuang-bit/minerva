"""Load ``skills/INDEX.md`` and per-skill ``SKILL.md`` text from the agent package."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_SKILLS_ROOT: Final[Path] = Path(__file__).resolve().parents[1] / "skills"
_INDEX_NAME: Final[str] = "INDEX.md"


def skills_root() -> Path:
    """Return the absolute ``backend/app/agent/skills`` directory."""

    return _SKILLS_ROOT


def load_index_text() -> str:
    """Read and return the root ``INDEX.md`` body."""

    path = _SKILLS_ROOT / _INDEX_NAME
    if not path.is_file():
        raise FileNotFoundError(f"missing skills index: {path}")
    return path.read_text(encoding="utf-8")


def parse_skill_ids_from_index(index_text: str) -> list[str]:
    """Parse bullet skill ids from index markdown (``- id`` or ``- `id`：...``)."""

    ids: list[str] = []
    for raw in index_text.splitlines():
        line = raw.strip()
        m = re.match(r"^[-*]\s+`?([a-z0-9_]+)`?", line, re.I)
        if m:
            ids.append(m.group(1).lower())
    return ids


def parse_skill_descriptions_from_index(index_text: str) -> dict[str, str]:
    """Parse ``- `id`：description`` bullets into a map."""

    out: dict[str, str] = {}
    for raw in index_text.splitlines():
        line = raw.strip()
        m = re.match(r"^[-*]\s+`?([a-z0-9_]+)`?\s*[：:]\s*(.+)$", line, re.I)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def list_indexed_skills() -> list[dict[str, str]]:
    """Return skills from INDEX that have an on-disk ``SKILL.md``."""

    index_text = load_index_text()
    ids = parse_skill_ids_from_index(index_text)
    desc_map = parse_skill_descriptions_from_index(index_text)
    items: list[dict[str, str]] = []
    for sid in ids:
        skill_md = _SKILLS_ROOT / sid / "SKILL.md"
        if not skill_md.is_file():
            continue
        items.append({"id": sid, "description": desc_map.get(sid) or sid})
    return items


def load_skill_markdown(skill_id: str) -> str:
    """Return ``SKILL.md`` contents for ``skill_id`` subdirectory."""

    sid = skill_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]+", sid):
        raise ValueError("invalid skill_id")
    path = _SKILLS_ROOT / sid / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"missing SKILL.md for skill: {sid}")
    return path.read_text(encoding="utf-8")
