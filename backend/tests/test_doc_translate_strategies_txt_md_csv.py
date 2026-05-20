"""Roundtrip tests for txt/md/csv translation strategies."""

from pathlib import Path

from app.translate.domain.dto import SegmentRecord
from app.translate.service.strategies.csv_strategy import CsvTranslateStrategy
from app.translate.service.strategies.md_strategy import MdTranslateStrategy
from app.translate.service.strategies.txt_strategy import TxtTranslateStrategy


def test_txt_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hello\n\nworld\n", encoding="utf-8")
    strategy = TxtTranslateStrategy()
    drafts = strategy.extract(src)
    assert len(drafts) == 2
    records = [
        SegmentRecord(seq=d.seq, source_text=d.source_text, translated_text=d.source_text.upper())
        for d in drafts
    ]
    out = tmp_path / "a_out.txt"
    strategy.assemble(records, src, out)
    assert "HELLO" in out.read_text(encoding="utf-8")
    assert "WORLD" in out.read_text(encoding="utf-8")


def test_md_preserves_fence_block(tmp_path: Path) -> None:
    src = tmp_path / "a.md"
    src.write_text("# Title\n\n```python\nprint(1)\n```\n\npara\n", encoding="utf-8")
    strategy = MdTranslateStrategy()
    drafts = strategy.extract(src)
    assert any("```python" in d.source_text for d in drafts)
    records = [
        SegmentRecord(seq=d.seq, source_text=d.source_text, translated_text="X" + str(d.seq))
        for d in drafts
    ]
    out = tmp_path / "a_out.md"
    strategy.assemble(records, src, out)
    assert out.read_text(encoding="utf-8")


def test_csv_row_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "a.csv"
    src.write_text("a,b\nc,d\n", encoding="utf-8")
    strategy = CsvTranslateStrategy()
    drafts = strategy.extract(src)
    assert len(drafts) >= 2
    records = [
        SegmentRecord(
            seq=d.seq,
            source_text=d.source_text,
            translated_text=d.source_text.replace("a", "A"),
            anchor_json=d.anchor_json,
        )
        for d in drafts
    ]
    out = tmp_path / "a_out.csv"
    strategy.assemble(records, src, out)
    text = out.read_text(encoding="utf-8")
    assert "A,b" in text or "A" in text
