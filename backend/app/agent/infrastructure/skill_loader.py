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


def load_skill_markdown(skill_id: str) -> str:
    """Return ``SKILL.md`` contents for ``skill_id`` subdirectory."""

    sid = skill_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]+", sid):
        raise ValueError("invalid skill_id")
    path = _SKILLS_ROOT / sid / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"missing SKILL.md for skill: {sid}")
    return path.read_text(encoding="utf-8")
