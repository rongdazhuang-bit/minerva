"""Pydantic request shapes exposed by ``llm`` routers."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.llm.domain.models import ProviderKind


class ChatMessageIn(BaseModel):
    """Inbound chat message tuple mirroring OpenAI chat payloads."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request (internal HTTP surface)."""

    provider_kind: ProviderKind = ProviderKind.openai_compatible
    base_url: str = Field(min_length=1, description="OpenAI-compatible API root, e.g. http://localhost:4000/v1")
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    system_prompt: str | None = None
    user_prompt: str | None = None
    messages: list[ChatMessageIn] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
