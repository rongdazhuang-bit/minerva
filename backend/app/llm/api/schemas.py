"""Pydantic request shapes exposed by ``llm`` routers."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    """Inbound chat message tuple mirroring OpenAI chat payloads."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request resolved via workspace model_id."""

    model_id: uuid.UUID
    system_prompt: str | None = None
    user_prompt: str | None = None
    messages: list[ChatMessageIn] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    n: int | None = Field(default=None, ge=1)
    stop: list[str] | str | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    stream: bool = True


class EmbeddingRequest(BaseModel):
    """Embedding request resolved via workspace model_id."""

    model_id: uuid.UUID
    input: str | list[str]
    dimensions: int | None = Field(default=None, ge=1)
    encoding_format: str = "float"


class RerankRequest(BaseModel):
    """Rerank request resolved via workspace model_id."""

    model_id: uuid.UUID
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)
    top_n: int | None = Field(default=None, ge=1)
