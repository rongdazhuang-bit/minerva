"""Tests for CSV translation strategy behavior."""

from pathlib import Path

from app.translate.domain.dto import SegmentRecord
from app.translate.service.strategies.csv_strategy import CsvTranslateStrategy


def test_csv_translates_fields_without_changing_shape(tmp_path: Path) -> None:
    """Translate CSV data fields while keeping rows and quoting structure valid."""
    source = tmp_path / "source.csv"
    output = tmp_path / "output.csv"
    source.write_text('name,desc\n"apple","red, sweet"\n', encoding="utf-8-sig")

    strategy = CsvTranslateStrategy()
    drafts = strategy.extract(source)

    assert any(
        d.anchor_json == {"row": 1, "field_index": 0, "label": "csv_field"} for d in drafts
    )
    assert any(
        d.anchor_json == {"row": 1, "field_index": 1, "label": "csv_field"} for d in drafts
    )

    records = [
        SegmentRecord(
            seq=d.seq,
            source_text=d.source_text,
            translated_text=f"译:{d.source_text}",
            anchor_json=d.anchor_json,
        )
        for d in drafts
    ]
    strategy.assemble(records, source, output)

    written = output.read_text(encoding="utf-8-sig")
    assert written.splitlines()[0] == "name,desc"
    assert '"译:apple"' in written
    assert '"译:red, sweet"' in written
    assert len(written.splitlines()[1].split(",")) >= 3
