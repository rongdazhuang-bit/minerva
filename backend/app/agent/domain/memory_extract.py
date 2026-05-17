"""Structured output for long-term memory persistence."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryFactItem(BaseModel):
    """One extractable fact for ``agent_long_term_memory``."""

    key: str | None = None
    content: str
    tags: list[str] = Field(default_factory=list)


class MemoryExtract(BaseModel):
    """LLM output for ``memory.persist`` node."""

    summary: str = Field(description="One-sentence summary of the turn.")
    facts: list[MemoryFactItem] = Field(
        default_factory=list,
        description="0-5 reusable facts; empty if none.",
    )
