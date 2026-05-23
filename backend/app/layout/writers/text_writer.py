"""Writers for plain text and Markdown-like ordered segment output."""

from __future__ import annotations

from app.layout.writers.base import WriteContext


class OrderedTextWriter:
    """Write records in sequence separated by blank lines."""

    def write(self, context: WriteContext) -> None:
        """Write ordered translated records while preserving skip-marked source text."""
        ordered = sorted(context.segments, key=lambda s: s.seq)
        parts = [
            s.source_text if (s.anchor_json or {}).get("skip_translate") else s.translated_text
            for s in ordered
        ]
        context.out_path.write_text(
            "\n\n".join((p or "") for p in parts),
            encoding="utf-8",
        )
