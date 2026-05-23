"""Domain primitives shared between AI strategies and HTTP schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProviderKind(str, Enum):
    """Upstream vendor discriminator stored on HTTP requests."""

    openai = "openai"
    volcengine = "volcengine"
    aliyun = "aliyun"


class ChatMessage(BaseModel):
    """Single chat message; content aligns with OpenAI chat message text content."""

    role: str
    content: str


class ChatCallParams(BaseModel):
    """Normalized call parameters passed to a completion strategy.

    ``messages`` follows the OpenAI Chat Completions shape (e.g. ``role`` + ``content``,
    or ``tool_calls`` / ``tool`` roles). ``tools`` and ``tool_choice`` are optional and
    omitted by legacy callers.
    """

    base_url: str = Field(
        description="Full OpenAI-compatible chat completions URL configured for the model."
    )
    api_key: str
    model: str
    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="OpenAI-style chat messages (plain or tool-calling shapes).",
    )
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
