"""Domain primitives shared between AI strategies and HTTP schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ProviderKind(str, Enum):
    """Upstream vendor discriminator stored on HTTP requests."""

    openai_compatible = "openai_compatible"
    volcengine = "volcengine"
    aliyun = "aliyun"


class ChatMessage(BaseModel):
    """Single chat message; content aligns with OpenAI chat message text content."""

    role: str
    content: str


class ChatCallParams(BaseModel):
    """Normalized call parameters passed to a completion strategy."""

    base_url: str = Field(description="OpenAI-compatible root, e.g. https://host/v1 for LiteLLM.")
    api_key: str
    model: str
    messages: list[dict[str, str]] = Field(
        default_factory=list,
        description="OpenAI-style messages: list of {role, content}.",
    )
    temperature: float | None = None
    max_tokens: int | None = None
