"""Filesystem CRUD for global agent skill packages."""

from __future__ import annotations

import io
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from app.agent.infrastructure.skill_loader import (
    IndexedSkill,
    invalidate_skill_cache,
    load_index_json,
    parse_index_skills,
    skills_root,
)
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
        if path.name == "INDEX.json":
            invalidate_skill_cache(None)
        elif skill_id and skill_id != "INDEX.json":
            invalidate_skill_cache(skill_id if path.name == "tools.py" else None)
        else:
            invalidate_skill_cache(None)
        return True

    @staticmethod
    def _should_skip_path(path: Path) -> bool:
        """Return True for ``__pycache__`` segments and ``.pyc`` files."""

        return any(part == "__pycache__" for part in path.parts) or path.suffix.lower() == ".pyc"

    @staticmethod
    def _should_skip_zip_entry(name: str) -> bool:
        """Return True for zip members under ``__pycache__`` or ending in ``.pyc``."""

        normalized = name.replace("\\", "/").strip("/")
        if not normalized:
            return True
        parts = normalized.split("/")
        return any(part == "__pycache__" for part in parts) or normalized.endswith(".pyc")

    def _count_skill_files(self, skill_id: str) -> int:
        """Count non-skipped files under one skill directory."""

        skill_dir = self.root / skill_id
        if not skill_dir.is_dir():
            return 0
        return sum(1 for path in skill_dir.rglob("*") if path.is_file() and not self._should_skip_path(path))

    def _discover_local_skills(self) -> list[IndexedSkill]:
        """List skill subdirs under ``self.root`` that contain ``SKILL.md``."""

        found: list[IndexedSkill] = []
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if (child / "SKILL.md").is_file():
                found.append(
                    IndexedSkill(
                        id=child.name,
                        description=child.name,
                        composer_description=child.name,
                        composer_visible=True,
                    )
                )
        return found

    def list_registry(self) -> list[dict[str, object]]:
        """List indexed skills with id, description, and on-disk file counts."""

        data = load_index_json(self.root)
        if data and isinstance(data.get("skills"), list):
            entries = [
                entry
                for entry in parse_index_skills(data, root=self.root)
                if (self.root / entry.id).is_dir()
            ]
        else:
            entries = self._discover_local_skills()
        registry: list[dict[str, object]] = []
        for entry in entries:
            registry.append(
                {
                    "id": entry.id,
                    "description": entry.description,
                    "composer_description": entry.composer_description,
                    "composer_visible": entry.composer_visible,
                    "file_count": self._count_skill_files(entry.id),
                }
            )
        return registry

    def build_tree(self, skill_id: str) -> list[dict[str, object]]:
        """Return a nested file tree for one skill directory."""

        sid = self.validate_skill_id(skill_id)
        skill_dir = self.root / sid
        if not skill_dir.is_dir():
            raise AppError("skills.not_found", "Skill not found", 404)
        nodes: list[dict[str, object]] = []
        for child in sorted(skill_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if self._should_skip_path(child):
                continue
            nodes.append(self._build_tree_node(child))
        return nodes

    def _build_tree_node(self, path: Path) -> dict[str, object]:
        """Build one tree node with relative path from ``self.root``."""

        rel = path.relative_to(self.root).as_posix()
        if path.is_dir():
            children: list[dict[str, object]] = []
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if self._should_skip_path(child):
                    continue
                children.append(self._build_tree_node(child))
            return {
                "name": path.name,
                "path": rel,
                "is_dir": True,
                "size": None,
                "children": children,
            }
        return {
            "name": path.name,
            "path": rel,
            "is_dir": False,
            "size": path.stat().st_size,
            "children": [],
        }

    def _invalidate_after_delete(self, rel: str) -> None:
        """Clear skill_loader caches after a path removal."""

        parts = rel.split("/")
        if not parts:
            return
        if parts[0] == "INDEX.json" or rel == "INDEX.json":
            invalidate_skill_cache(None)
            return
        if len(parts) == 1:
            invalidate_skill_cache(parts[0])
            return
        if parts[1] == "tools.py":
            invalidate_skill_cache(parts[0])
            return
        invalidate_skill_cache(None)

    def delete_path(self, rel: str) -> bool:
        """Recursively delete a file or directory under the skills root."""

        path = self.resolve_relative(rel)
        if not path.exists():
            raise AppError("skills.not_found", "Path not found", 404)
        rel_norm = path.relative_to(self.root).as_posix()
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        self._invalidate_after_delete(rel_norm)
        return True

    def delete_skill(self, skill_id: str) -> bool:
        """Delete an entire skill package directory."""

        sid = self.validate_skill_id(skill_id)
        skill_dir = self.root / sid
        if not skill_dir.is_dir():
            raise AppError("skills.not_found", "Skill not found", 404)
        shutil.rmtree(skill_dir)
        invalidate_skill_cache(sid)
        return True

    def upload_skill_zip(self, data: bytes) -> dict[str, str]:
        """Validate and install a zip whose root is exactly one skill directory."""

        tmp_dir = self.root / ".tmp" / str(uuid.uuid4())
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        name = info.filename.replace("\\", "/")
                        if self._should_skip_zip_entry(name):
                            continue
                        if ".." in name.split("/"):
                            raise AppError("skills.zip_invalid", "Invalid zip entry path", 400)
                        target = (tmp_dir / name).resolve()
                        if not str(target).startswith(str(tmp_dir.resolve())):
                            raise AppError("skills.zip_invalid", "Invalid zip entry path", 400)
                        if info.is_dir() or name.endswith("/"):
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(zf.read(info))
            except zipfile.BadZipFile as e:
                raise AppError("skills.zip_invalid", "Invalid zip archive", 400) from e

            root_entries = [entry for entry in tmp_dir.iterdir() if not self._should_skip_path(entry)]
            root_dirs = [entry for entry in root_entries if entry.is_dir()]
            if len(root_dirs) != 1 or len(root_entries) != 1:
                raise AppError("skills.zip_invalid", "Zip must contain exactly one root directory", 400)

            skill_id = self.validate_skill_id(root_dirs[0].name)
            dest = self.root / skill_id
            if dest.exists():
                raise AppError("skills.duplicate", f"Skill already exists: {skill_id}", 409)
            if not (root_dirs[0] / "SKILL.md").is_file():
                raise AppError("skills.zip_invalid", "Skill package must contain SKILL.md", 400)

            shutil.move(str(root_dirs[0]), str(dest))
            invalidate_skill_cache(skill_id)
            return {"skill_id": skill_id}
        finally:
            if tmp_dir.is_dir():
                shutil.rmtree(tmp_dir, ignore_errors=True)
