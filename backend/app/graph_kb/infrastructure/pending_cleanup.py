"""Persist GraphKB cleanup intents when Celery enqueue fails (spec §5.7 retry)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.log import get_logger

log = get_logger(__name__)

_PENDING_DIR_NAME = ".pending_cleanup"


def _pending_dir() -> Path:
    """Return (and create) the directory for deferred cleanup JSON files."""

    root = settings.resolve_graph_kb_data() / _PENDING_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _pending_path(*, workspace_id: uuid.UUID, graph_id: uuid.UUID) -> Path:
    """Path for one pending cleanup record."""

    return _pending_dir() / f"{workspace_id}_{graph_id}.json"


def record_pending_cleanup(
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    engine: str,
) -> None:
    """Write a pending cleanup file so a later flush can enqueue Celery work."""

    payload = {
        "workspace_id": str(workspace_id),
        "graph_id": str(graph_id),
        "engine": engine,
    }
    path = _pending_path(workspace_id=workspace_id, graph_id=graph_id)
    path.write_text(json.dumps(payload), encoding="utf-8")
    log.warning(
        "graph_kb.cleanup pending graph_id={} engine={} path={}",
        graph_id,
        engine,
        path,
    )


def clear_pending_cleanup(*, workspace_id: uuid.UUID, graph_id: uuid.UUID) -> None:
    """Remove the pending file after cleanup succeeds or is re-enqueued."""

    path = _pending_path(workspace_id=workspace_id, graph_id=graph_id)
    if path.is_file():
        path.unlink(missing_ok=True)


def iter_pending_cleanups() -> list[dict[str, Any]]:
    """Load all pending cleanup payloads from disk."""

    directory = _pending_dir()
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("graph_kb.cleanup pending_read_failed path={}", path)
            continue
        if isinstance(raw, dict):
            entries.append(raw)
    return entries
