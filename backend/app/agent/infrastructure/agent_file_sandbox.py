"""Workspace-scoped local filesystem sandbox for the ``file`` agent skill."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from app.config import resolve_agent_files_root, settings

_MAX_SEGMENT_LEN = 255
_MAX_PATH_LEN = 4096

# Case-folded path segment names that mimic OS/system directories (Linux FHS + Windows).
_OS_RESERVED_SEGMENTS: frozenset[str] = frozenset(
    {
        "bin",
        "boot",
        "dev",
        "documents and settings",
        "etc",
        "lib",
        "lib64",
        "media",
        "mnt",
        "opt",
        "perflogs",
        "proc",
        "program files",
        "program files (x86)",
        "programdata",
        "recovery",
        "root",
        "run",
        "sbin",
        "srv",
        "sys",
        "syswow64",
        "system32",
        "usr",
        "var",
        "winnt",
        "windows",
        "users",
        "appdata",
        "config.msi",
        "recycler",
        "$recycle.bin",
    }
)

# Windows reserved device names (case-insensitive), per segment.
_WINDOWS_DEVICE_NAMES: frozenset[str] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)


class AgentFileSandbox:
    """Resolve relative paths under one workspace directory and perform FS operations."""

    class Error(Exception):
        """Structured sandbox failure with a stable machine-readable ``code``."""

        def __init__(self, code: str, message: str) -> None:
            """Store ``code`` and human-readable ``message``."""

            super().__init__(message)
            self.code = code
            self.message = message

        def to_dict(self) -> dict[str, object]:
            """Return JSON-serializable error payload for tool handlers."""

            return {"ok": False, "error": self.message, "code": self.code}

    def __init__(self, *, workspace_id: uuid.UUID) -> None:
        """Bind sandbox to one workspace id under the global agent files root."""

        self._workspace_id = workspace_id
        root = resolve_agent_files_root()
        self._root = root / "workspaces" / str(workspace_id)

    def workspace_root(self) -> Path:
        """Ensure workspace sandbox root exists and return it."""

        self._root.mkdir(parents=True, exist_ok=True)
        return self._root

    def resolve(self, path: str) -> Path:
        """Normalize ``path`` and return an absolute path inside the workspace root."""

        normalized = _normalize_relative_path(path)
        workspace_root = self.workspace_root().resolve()
        if not normalized:
            return workspace_root
        parts = [p for p in normalized.split("/") if p]
        _assert_segments_not_os_reserved(parts)
        for part in parts:
            if len(part) > _MAX_SEGMENT_LEN:
                raise self.Error("path_invalid", "path segment too long")
        joined = "/".join(parts)
        if len(joined) > _MAX_PATH_LEN:
            raise self.Error("path_invalid", "path too long")
        resolved = (workspace_root / Path(*parts)).resolve()
        if not resolved.is_relative_to(workspace_root):
            raise self.Error("path_outside_sandbox", "path outside workspace sandbox")
        return resolved

    def list_dir(self, path: str = "") -> dict[str, object]:
        """List immediate children of a directory."""

        target = self.resolve(path)
        if not target.exists():
            raise self.Error("not_found", "path not found")
        if not target.is_dir():
            raise self.Error("not_a_directory", "path is not a directory")
        entries: list[dict[str, object]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            entry: dict[str, object] = {
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
            }
            if child.is_file():
                entry["size"] = child.stat().st_size
            entries.append(entry)
        rel = _relative_display(self.workspace_root(), target)
        return {"ok": True, "path": rel, "entries": entries}

    def read_file(self, path: str) -> dict[str, object]:
        """Read a UTF-8 text file up to ``agent_file_max_bytes``."""

        target = self.resolve(path)
        if not target.exists():
            raise self.Error("not_found", "path not found")
        if target.is_dir():
            raise self.Error("is_directory", "path is a directory")
        size = target.stat().st_size
        max_bytes = settings.agent_file_max_bytes
        if size > max_bytes:
            raise self.Error("too_large", f"file exceeds {max_bytes} bytes")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise self.Error("not_utf8", "file is not valid UTF-8 text") from e
        rel = _relative_display(self.workspace_root(), target)
        return {"ok": True, "path": rel, "content": content, "size": size}

    def write_file(
        self,
        path: str,
        content: str,
        *,
        create_parents: bool = True,
    ) -> dict[str, object]:
        """Create or overwrite a UTF-8 text file."""

        target = self.resolve(path)
        if target.exists() and target.is_dir():
            raise self.Error("is_directory", "path is a directory")
        encoded = content.encode("utf-8")
        if len(encoded) > settings.agent_file_max_bytes:
            raise self.Error("too_large", f"content exceeds {settings.agent_file_max_bytes} bytes")
        created = not target.exists()
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            raise self.Error("not_found", "parent directory does not exist")
        target.write_bytes(encoded)
        rel = _relative_display(self.workspace_root(), target)
        return {"ok": True, "path": rel, "size": len(encoded), "created": created}

    def delete_path(self, path: str, *, recursive: bool = False) -> dict[str, object]:
        """Delete a file or directory."""

        target = self.resolve(path)
        if not target.exists():
            raise self.Error("not_found", "path not found")
        rel = _relative_display(self.workspace_root(), target)
        if target.is_file():
            target.unlink()
            return {"ok": True, "path": rel, "deleted": True}
        if any(target.iterdir()) and not recursive:
            raise self.Error("directory_not_empty", "directory is not empty")
        shutil.rmtree(target)
        return {"ok": True, "path": rel, "deleted": True}

    def mkdir(self, path: str, *, parents: bool = True) -> dict[str, object]:
        """Create a directory."""

        target = self.resolve(path)
        if target.exists():
            if target.is_dir():
                rel = _relative_display(self.workspace_root(), target)
                return {"ok": True, "path": rel, "created": False}
            raise self.Error("already_exists", "path exists and is not a directory")
        if parents:
            target.mkdir(parents=True, exist_ok=True)
        else:
            if not target.parent.exists():
                raise self.Error("not_found", "parent directory does not exist")
            target.mkdir()
        rel = _relative_display(self.workspace_root(), target)
        return {"ok": True, "path": rel, "created": True}

    def move_path(self, src: str, dest: str) -> dict[str, object]:
        """Rename or move ``src`` to ``dest`` within the sandbox."""

        src_path = self.resolve(src)
        if not src_path.exists():
            raise self.Error("not_found", "source path not found")
        dest_path = self.resolve(dest)
        if dest_path.exists():
            raise self.Error("dest_exists", "destination already exists")
        if not dest_path.parent.exists():
            raise self.Error("not_found", "destination parent directory does not exist")
        src_rel = _relative_display(self.workspace_root(), src_path)
        dest_rel = _relative_display(self.workspace_root(), dest_path)
        src_path.rename(dest_path)
        return {"ok": True, "src": src_rel, "dest": dest_rel}

    async def list_dir_async(self, path: str = "") -> dict[str, object]:
        """Run ``list_dir`` in a worker thread."""

        return await asyncio.to_thread(self.list_dir, path)

    async def read_file_async(self, path: str) -> dict[str, object]:
        """Run ``read_file`` in a worker thread."""

        return await asyncio.to_thread(self.read_file, path)

    async def write_file_async(
        self,
        path: str,
        content: str,
        *,
        create_parents: bool = True,
    ) -> dict[str, object]:
        """Run ``write_file`` in a worker thread."""

        return await asyncio.to_thread(
            self.write_file,
            path,
            content,
            create_parents=create_parents,
        )

    async def delete_path_async(self, path: str, *, recursive: bool = False) -> dict[str, object]:
        """Run ``delete_path`` in a worker thread."""

        return await asyncio.to_thread(self.delete_path, path, recursive=recursive)

    async def mkdir_async(self, path: str, *, parents: bool = True) -> dict[str, object]:
        """Run ``mkdir`` in a worker thread."""

        return await asyncio.to_thread(self.mkdir, path, parents=parents)

    async def move_path_async(self, src: str, dest: str) -> dict[str, object]:
        """Run ``move_path`` in a worker thread."""

        return await asyncio.to_thread(self.move_path, src, dest)


def _normalize_relative_path(path: str) -> str:
    """Normalize user path to a safe relative form (empty string means workspace root)."""

    raw = (path or "").strip().replace("\\", "/")
    if raw in ("", "."):
        return ""
    while raw.startswith("/"):
        raw = raw[1:]
    if raw.startswith("~"):
        raise AgentFileSandbox.Error("path_invalid", "path must be relative")
    if len(raw) >= 2 and raw[1] == ":":
        raise AgentFileSandbox.Error("path_invalid", "absolute paths are not allowed")
    segments = [p for p in raw.split("/") if p != ""]
    if any(seg == ".." for seg in segments):
        raise AgentFileSandbox.Error("path_invalid", "path must not contain '..'")
    if any(seg in (".", "") for seg in segments):
        raise AgentFileSandbox.Error("path_invalid", "invalid path segment")
    _assert_segments_not_os_reserved(segments)
    return "/".join(segments)


def _assert_segments_not_os_reserved(segments: list[str]) -> None:
    """Reject path segments that name OS/system directories or Windows devices."""

    for seg in segments:
        key = seg.casefold()
        if key in _OS_RESERVED_SEGMENTS:
            raise AgentFileSandbox.Error(
                "os_path_forbidden",
                f"os reserved path segment is not allowed: {seg}",
            )
        base = key.split(".", 1)[0]
        if base in _WINDOWS_DEVICE_NAMES:
            raise AgentFileSandbox.Error(
                "os_path_forbidden",
                f"reserved device name is not allowed: {seg}",
            )


def _relative_display(workspace_root: Path, target: Path) -> str:
    """Return display path relative to workspace root (``""`` for root)."""

    rel = target.resolve().relative_to(workspace_root.resolve())
    if rel.as_posix() == ".":
        return ""
    return rel.as_posix()
