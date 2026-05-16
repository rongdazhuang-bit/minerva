"""Typed schema for the ``minerva`` extension on OpenAI-compatible SSE chunks."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

MINERVA_SSE_SCHEMA_VERSION: Literal[1] = 1


class MinervaStreamEventKind(str, Enum):
    """Discriminator for orchestration events embedded in SSE chunks."""

    run_started = "run.started"
    run_finished = "run.finished"
    run_error = "run.error"
    node_updated = "node.updated"
    tool_start = "tool.start"
    tool_result = "tool.result"


class MinervaNodeStatus(str, Enum):
    """Lifecycle status mirrored from ``agent_run_node.status``."""

    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"


class MinervaNodeSnapshot(BaseModel):
    """Lightweight node view for live UI traces (not a full DB row)."""

    id: UUID
    parent_node_id: UUID | None = None
    node_type: str
    node_name: str
    status: MinervaNodeStatus
    sequence_idx: int | None = None


class MinervaToolSnapshot(BaseModel):
    """Tool invocation metadata for SSE (arguments/results are redacted previews)."""

    tool_call_id: str
    name: str
    arguments_preview: str | None = None
    result_preview: str | None = None


class MinervaErrorPayload(BaseModel):
    """Machine-oriented error surfaced on the event stream."""

    code: str
    message: str


class MinervaChunkExtension(BaseModel):
    """Root ``minerva`` object on synthetic orchestration chunks (schema v1)."""

    v: Literal[1] = MINERVA_SSE_SCHEMA_VERSION
    event: MinervaStreamEventKind
    run_id: UUID
    ts: str
    session_id: UUID | None = None
    status: Literal["success", "failed"] | None = None
    node: MinervaNodeSnapshot | None = None
    tool: MinervaToolSnapshot | None = None
    error: MinervaErrorPayload | None = None

    @model_validator(mode="after")
    def _payload_matches_event(self) -> Self:
        """Ensure required nested payloads exist for each event kind."""

        ev = self.event
        if ev == MinervaStreamEventKind.run_started:
            if self.session_id is None:
                raise ValueError("run.started requires session_id")
        elif ev == MinervaStreamEventKind.run_finished:
            if self.status is None:
                raise ValueError("run.finished requires status")
        elif ev == MinervaStreamEventKind.run_error:
            if self.error is None:
                raise ValueError("run.error requires error")
        elif ev == MinervaStreamEventKind.node_updated:
            if self.node is None:
                raise ValueError("node.updated requires node")
        elif ev in (MinervaStreamEventKind.tool_start, MinervaStreamEventKind.tool_result):
            if self.tool is None:
                raise ValueError(f"{ev.value} requires tool")
        return self


def utc_iso_now() -> str:
    """Return current UTC timestamp as ISO-8601 with ``Z`` suffix."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def minerva_extension_to_dict(ext: MinervaChunkExtension) -> dict[str, Any]:
    """Serialize extension for embedding in a chunk JSON object."""

    return ext.model_dump(mode="json")
