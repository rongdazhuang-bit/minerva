"""Per-run context passed into skill ``register_tools`` handlers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


@dataclass(frozen=True)
class SkillToolContext:
    """Workspace-scoped context for loading skill tools on demand."""

    workspace_id: uuid.UUID
    chat_model: BaseChatModel | None = None
