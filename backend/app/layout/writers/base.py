"""Common writer contracts for layout-aware document translation output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from app.translate.domain.dto import SegmentRecord

if TYPE_CHECKING:
    from app.layout.models import LayoutDocument


@dataclass(frozen=True)
class WriteContext:
    """Inputs required to assemble one translated document."""

    source_path: Path
    out_path: Path
    segments: list[SegmentRecord]
    layout_document: LayoutDocument | None = None


class LayoutWriter(Protocol):
    """Write translated segments back into one output file."""

    def write(self, context: WriteContext) -> None:
        """Create ``context.out_path`` from source, layout snapshot, and translated segments."""
