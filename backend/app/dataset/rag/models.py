"""Lightweight document objects for extraction and indexing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagDocument:
    """One text unit flowing through extract → clean → split → index."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
