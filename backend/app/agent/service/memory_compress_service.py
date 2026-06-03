"""Batch compression of old mem0 memories via mem0 LLM config."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import create_engine, nulls_last, select

from app.agent.domain.db.models import AgentSession
from app.agent.memory.mem0.client import get_mem0_memory
from app.agent.service.mem0_llm_client import mem0_llm_complete
from app.config import settings

log = logging.getLogger(__name__)

_COMPRESS_SYSTEM_PROMPT = (
    "Merge the following memory snippets into one concise summary in the same language "
    "as the source text. Preserve facts and preferences; omit redundancy. "
    "Output plain text only, no bullet list unless necessary."
)

_SESSION_SCAN_LIMIT = 500


def _parse_created_at(value: Any) -> datetime | None:
    """Parse mem0 ``created_at`` into UTC datetime."""

    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _list_session_pairs() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Load workspace/session ids to scan (sync SQLAlchemy)."""

    engine = create_engine(
        settings.sync_database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        future=True,
    )
    with engine.connect() as conn:
        rows = conn.execute(
            select(AgentSession.workspace_id, AgentSession.id)
            .order_by(nulls_last(AgentSession.updated_at.desc()))
            .limit(_SESSION_SCAN_LIMIT)
        ).all()
    return [(row[0], row[1]) for row in rows]


def _compress_session(
    memory: Any,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    cutoff: datetime,
) -> dict[str, int]:
    """Merge memories older than ``cutoff`` for one session; return per-session stats."""

    stats = {"scanned": 0, "merged": 0, "deleted": 0}
    raw = memory.get_all(
        user_id=str(workspace_id),
        run_id=str(session_id),
        limit=500,
    )
    results = raw.get("results") if isinstance(raw, dict) else raw
    if not results:
        return stats

    old_items: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        stats["scanned"] += 1
        created = _parse_created_at(item.get("created_at"))
        if created is not None and created < cutoff:
            old_items.append(item)

    if len(old_items) < 2:
        return stats

    lines = []
    for item in old_items:
        text_val = (item.get("memory") or item.get("text") or "").strip()
        if text_val:
            lines.append(f"- {text_val[:500]}")
    if not lines:
        return stats

    try:
        summary = mem0_llm_complete(
            system_prompt=_COMPRESS_SYSTEM_PROMPT,
            user_prompt="\n".join(lines),
        )
    except Exception:
        log.exception(
            "mem0 compress LLM failed workspace=%s session=%s",
            workspace_id,
            session_id,
        )
        return stats

    if not summary:
        return stats

    memory.add(
        [
            {
                "role": "user",
                "content": f"[compressed memory batch] {summary[:4000]}",
            }
        ],
        user_id=str(workspace_id),
        run_id=str(session_id),
        infer=False,
        metadata={"source": "agent.memory.compress_mem0"},
    )
    stats["merged"] = 1

    for item in old_items:
        mid = item.get("id")
        if not mid:
            continue
        try:
            memory.delete(str(mid))
            stats["deleted"] += 1
        except Exception:
            log.warning(
                "mem0 delete failed id=%s workspace=%s session=%s",
                mid,
                workspace_id,
                session_id,
                exc_info=True,
            )
    return stats


def run_mem0_memory_compress() -> dict[str, object]:
    """Scan recent sessions and compress mem0 memories older than configured age."""

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.agent_memory_compress_max_age_days
    )
    memory = get_mem0_memory()
    totals = {
        "sessions_scanned": 0,
        "sessions_merged": 0,
        "memories_scanned": 0,
        "memories_deleted": 0,
        "cutoff": cutoff.isoformat(),
    }

    try:
        pairs = _list_session_pairs()
    except Exception:
        log.exception("mem0 compress failed to list agent sessions")
        totals["error"] = "session_list_failed"
        return totals

    for workspace_id, session_id in pairs:
        totals["sessions_scanned"] += 1
        try:
            session_stats = _compress_session(
                memory,
                workspace_id=workspace_id,
                session_id=session_id,
                cutoff=cutoff,
            )
        except Exception:
            log.exception(
                "mem0 compress session failed workspace=%s session=%s",
                workspace_id,
                session_id,
            )
            continue
        totals["memories_scanned"] += session_stats["scanned"]
        totals["memories_deleted"] += session_stats["deleted"]
        if session_stats["merged"]:
            totals["sessions_merged"] += 1

    log.info("mem0 compress done %s", totals)
    return totals
