"""Domain primitives shared between AI strategies and HTTP schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Single chat message; content aligns with OpenAI chat message text content."""

    role: str
    content: str


class TextChatCallParams(BaseModel):
    """OpenAI Chat Completions call parameters (text and translate models)."""

    messages: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    n: int | None = None
    stop: list[str] | str | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


class TextChatResult(BaseModel):
    """Parsed OpenAI Chat Completions response."""

    id: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    choices: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    def assistant_text(self) -> str:
        """Extract assistant text from the first choice, if present."""

        if not self.choices:
            return ""
        message = self.choices[0].get("message") or {}
        content = message.get("content")
        return (content or "").strip() if isinstance(content, str) else ""


class EmbeddingCallParams(BaseModel):
    """OpenAI Embeddings API call parameters."""

    input: str | list[str]
    dimensions: int | None = None
    encoding_format: str = "float"


class EmbeddingResult(BaseModel):
    """Parsed OpenAI Embeddings response."""

    data: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RerankCallParams(BaseModel):
    """OpenAI-compatible rerank call parameters."""

    query: str
    documents: list[str] = Field(min_length=1)
    top_n: int | None = Field(default=None, ge=1)


class RerankResult(BaseModel):
    """Parsed OpenAI-compatible rerank response."""

    id: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
