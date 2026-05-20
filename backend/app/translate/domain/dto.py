"""DTOs shared by format strategies and the translation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SegmentDraft:
    """One extractable paragraph before persistence."""

    seq: int
    source_text: str
    anchor_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class SegmentRecord:
    """Segment with translation result used during assemble."""

    seq: int
    source_text: str
    translated_text: str
    anchor_json: dict[str, Any] | None = None
