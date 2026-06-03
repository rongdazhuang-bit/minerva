"""Shared memory hit type for retrieve strategies."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryHit:
    """One memory item returned to the planner or executor."""

    content: str
    kind: str
    source: str
    key: str | None = None
    memory_id: uuid.UUID | str | None = None
    score: float | None = None
