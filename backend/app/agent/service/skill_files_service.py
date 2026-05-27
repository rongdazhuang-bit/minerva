"""Filesystem CRUD for global agent skill packages."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.agent.infrastructure.skill_loader import invalidate_skill_cache, skills_root
from app.exceptions import AppError

_SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_RESERVED_SKILL_IDS = frozenset({"registry"})
_EDITABLE_SUFFIXES = {".md", ".py", ".json"}
_MAX_TEXT_BYTES = 2 * 1024 * 1024


class SkillFilesService:
    """Read/write skill files under a fixed root with path confinement."""

    def __init__(self, root: Path | None = None) -> None:
        """Bind to ``root`` or the built-in ``skills_root()`` directory."""

        self.root = (root or skills_root()).resolve()

    @staticmethod
    def validate_skill_id(skill_id: str) -> str:
        """Normalize and validate a skill directory id; reject reserved names."""

        sid = (skill_id or "").strip().lower()
        if not _SKILL_ID_RE.match(sid) or sid in _RESERVED_SKILL_IDS:
            raise AppError("skills.path_invalid", f"Invalid skill id: {skill_id}", 400)
        return sid

    def resolve_relative(self, rel: str) -> Path:
        """Resolve ``rel`` under ``self.root``; reject traversal and symlinks."""

        raw = (rel or "").strip().replace("\\", "/").lstrip("/")
        if not raw or ".." in raw.split("/"):
            raise AppError("skills.path_invalid", "Invalid path", 400)
        target = (self.root / raw).resolve()
        if not str(target).startswith(str(self.root)):
            raise AppError("skills.path_invalid", "Path escapes skills root", 400)
        if target.is_symlink():
            raise AppError("skills.path_invalid", "Symlinks not allowed", 400)
        return target

    def read_text(self, rel: str) -> str:
        """Read a UTF-8 text file up to 2 MiB; 404 when missing."""

        path = self.resolve_relative(rel)
        if not path.is_file():
            raise AppError("skills.not_found", "File not found", 404)
        data = path.read_bytes()
        if len(data) > _MAX_TEXT_BYTES:
            raise AppError("skills.path_invalid", "File too large", 400)
        return data.decode("utf-8")

    def write_text(self, rel: str, content: str) -> bool:
        """Write md/py/json under the root and invalidate skill_loader caches."""

        path = self.resolve_relative(rel)
        if path.suffix.lower() not in _EDITABLE_SUFFIXES:
            raise AppError("skills.not_editable", "File type not editable", 400)
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_TEXT_BYTES:
            raise AppError("skills.path_invalid", "File too large", 400)
        if path.suffix.lower() == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise AppError("skills.json_invalid", str(e), 400) from e
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        skill_id = path.relative_to(self.root).parts[0] if path.relative_to(self.root).parts else None
        if path.name == "INDEX.md":
            invalidate_skill_cache(None)
        elif skill_id and skill_id != "INDEX.md":
            invalidate_skill_cache(skill_id if path.name == "tools.py" else None)
        else:
            invalidate_skill_cache(None)
        return True
