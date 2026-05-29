"""Resolved upstream model credentials loaded from ``sys_models``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

CHAT_MODEL_TAGS = frozenset({"TEXT", "TRANSLATE"})
EMBEDDING_MODEL_TAGS = frozenset({"EMBEDDINGS"})
RERANK_MODEL_TAGS = frozenset({"RERANKING"})


class ResolvedModel(BaseModel):
    """Workspace-scoped model row normalized for strategy invocation."""

    model_id: UUID
    model_name: str = Field(description="Upstream model field sent to the provider.")
    endpoint_url: str = Field(description="Full provider URL; used as POST target.")
    api_key: str
