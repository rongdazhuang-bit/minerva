"""Writers for text-like formats that assemble translated segment output."""

from __future__ import annotations

import csv
from io import StringIO

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


class CsvFieldWriter:
    """Write translated CSV fields while preserving row and field positions."""

    def write(self, context: WriteContext) -> None:
        """Apply translated segments to their anchored CSV cells."""
        raw = context.source_path.read_text(encoding="utf-8-sig", errors="replace")
        rows = list(csv.reader(StringIO(raw)))
        by_cell: dict[tuple[int, int], str] = {}
        for seg in context.segments:
            anchor = seg.anchor_json or {}
            if "row" not in anchor or "field_index" not in anchor:
                continue
            by_cell[(int(anchor["row"]), int(anchor["field_index"]))] = (
                seg.source_text
                if anchor.get("skip_translate")
                else seg.translated_text or seg.source_text
            )

        for (row_idx, field_idx), value in by_cell.items():
            if 0 <= row_idx < len(rows) and 0 <= field_idx < len(rows[row_idx]):
                rows[row_idx][field_idx] = value

        buf = StringIO()
        if rows:
            csv.writer(buf, lineterminator="\n").writerow(rows[0])
            csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_ALL).writerows(rows[1:])
        context.out_path.write_text(buf.getvalue(), encoding="utf-8-sig")
