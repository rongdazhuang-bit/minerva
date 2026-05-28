"""Resolved upstream model credentials loaded from ``sys_models``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

CHAT_MODEL_TYPES = frozenset({"text", "translate"})
EMBEDDING_MODEL_TYPES = frozenset({"embedding"})
RERANK_MODEL_TYPES = frozenset({"rerank"})


class ResolvedModel(BaseModel):
    """Workspace-scoped model row normalized for strategy invocation."""

    model_id: UUID
    model_name: str = Field(description="Upstream model field sent to the provider.")
    model_type: str
    endpoint_url: str = Field(description="Full provider URL; used as POST target.")
    api_key: str
