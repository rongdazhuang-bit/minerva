"""Per-run context passed into skill ``register_tools`` handlers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillToolContext:
    """Workspace-scoped context for loading skill tools on demand."""

    workspace_id: uuid.UUID
