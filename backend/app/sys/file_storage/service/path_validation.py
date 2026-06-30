"""LOCAL storage path segment validation and workspace root resolution."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import resolve_file_storage_local_root
from app.exceptions import AppError

_LOCAL_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]*$")


def normalize_local_path_segment(value: str | None) -> str | None:
    """Trim and validate relative local_path; blank becomes None."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if (
        trimmed.startswith("/")
        or "\\" in trimmed
        or ".." in trimmed
        or "//" in trimmed
        or not _LOCAL_PATH_PATTERN.fullmatch(trimmed)
    ):
        raise AppError(
            "file_storage.local_path_invalid",
            "Invalid local_path segment",
            422,
        )
    return trimmed


def resolve_workspace_local_root(*, workspace_id: uuid.UUID) -> Path:
    """Return ``FILE_STORAGE_LOCAL_ROOT / workspace_id``."""
    return (resolve_file_storage_local_root() / str(workspace_id)).resolve()


def resolve_effective_local_root(
    *,
    workspace_id: uuid.UUID,
    local_path: str | None,
) -> Path:
    """Return directory root for object files under one workspace LOCAL config."""
    workspace_root = resolve_workspace_local_root(workspace_id=workspace_id)
    segment = normalize_local_path_segment(local_path)
    if segment is None:
        return workspace_root
    candidate = (workspace_root / segment).resolve()
    if workspace_root not in candidate.parents and candidate != workspace_root:
        raise AppError("local.path_escape", "Resolved path escapes workspace root", 422)
    return candidate


def resolve_object_file(
    *,
    workspace_id: uuid.UUID,
    local_path: str | None,
    object_key: str,
) -> Path:
    """Map object key to absolute file path with traversal guard."""
    root = resolve_effective_local_root(workspace_id=workspace_id, local_path=local_path)
    # object_key uses POSIX separators
    candidate = (root / Path(object_key)).resolve()
    if root not in candidate.parents and candidate != root:
        raise AppError("local.path_escape", "Object key escapes storage root", 422)
    return candidate
