"""OpenAI ``chat.completion.chunk`` models used for agent SSE synthesis."""

from __future__ import annotations

import time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.agent.domain.sse_minerva import MinervaChunkExtension, minerva_extension_to_dict


class OpenAiChunkChoiceDelta(BaseModel):
    """Streaming delta payload (subset of OpenAI fields we emit or forward)."""

    role: str | None = None
    content: str | None = None
    reasoning_content: str | None = None
    reasoning: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class OpenAiChunkChoice(BaseModel):
    """Single choice entry in a streaming chunk."""

    index: int = 0
    delta: OpenAiChunkChoiceDelta = Field(default_factory=OpenAiChunkChoiceDelta)
    finish_reason: str | None = None


class OpenAiChatCompletionChunk(BaseModel):
    """Synthetic or validated OpenAI-compatible streaming chunk envelope."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[OpenAiChunkChoice]
    minerva: MinervaChunkExtension | None = None

    def to_sse_dict(self) -> dict[str, Any]:
        """Dump to JSON-compatible dict, omitting null ``minerva`` when absent."""

        data = self.model_dump(mode="json", exclude_none=True)
        if self.minerva is not None:
            data["minerva"] = minerva_extension_to_dict(self.minerva)
        return data


def build_minerva_chunk(
    ext: MinervaChunkExtension,
    *,
    model: str,
    chunk_id: str | None = None,
) -> OpenAiChatCompletionChunk:
    """Build a synthetic chunk whose ``choices[0].delta`` is empty and ``minerva`` is set."""

    cid = chunk_id or f"minerva-{ext.run_id}"
    return OpenAiChatCompletionChunk(
        id=cid,
        created=int(time.time()),
        model=model,
        choices=[OpenAiChunkChoice(delta=OpenAiChunkChoiceDelta())],
        minerva=ext,
    )


def new_upstream_chunk_id(run_id: UUID) -> str:
    """Generate a stable-looking completion id prefix for passthrough chunks."""

    return f"chatcmpl-{run_id.hex[:24]}"
