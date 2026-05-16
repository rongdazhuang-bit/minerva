"""Run-scoped context passed into skill tool registration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillToolContext:
    """Immutable context for one agent run's tool handlers."""

    workspace_id: uuid.UUID
