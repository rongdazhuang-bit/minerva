"""SSE v2 event types and serialization for agent runs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import orjson

SSE_DONE_LINE = b"data: [DONE]\n\n"


class AgentSseEventType(str, Enum):
    """Discriminator for agent SSE v2 stream events."""

    run_started = "run.started"
    run_finished = "run.finished"
    run_error = "run.error"
    plan_created = "plan.created"
    plan_step_updated = "plan.step_updated"
    graph_node = "graph.node"
    subagent_started = "subagent.started"
    subagent_finished = "subagent.finished"
    llm_delta = "llm.delta"
    llm_usage = "llm.usage"
    tool_started = "tool.started"
    tool_finished = "tool.finished"
    memory_retrieved = "memory.retrieved"
    message_final = "message.final"  # Reserved; not emitted (assistant text uses llm.delta only).


def utc_iso_now() -> str:
    """Return current UTC time as ISO-8601 string."""

    return datetime.now(timezone.utc).isoformat()


def build_sse_event(
    *,
    event_type: AgentSseEventType,
    run_id: UUID | str,
    session_id: UUID | str | None,
    payload: dict[str, Any],
    ts: str | None = None,
) -> bytes:
    """Format one SSE ``data:`` line for agent v2."""

    envelope = {
        "v": 2,
        "type": event_type.value,
        "run_id": str(run_id),
        "session_id": str(session_id) if session_id else None,
        "ts": ts or utc_iso_now(),
        "payload": payload,
    }
    return b"data: " + orjson.dumps(envelope) + b"\n\n"
