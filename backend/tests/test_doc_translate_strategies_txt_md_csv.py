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
    text = out.read_text(encoding="utf-8")
    assert "HELLO" in text
    assert "WORLD" in text


def test_txt_extract_splits_numbered_clauses(tmp_path: Path) -> None:
    """Technical txt without blank lines between sub-clauses yields multiple segments."""

    src = tmp_path / "std.txt"
    src.write_text(
        "2 术语\n"
        "说明。\n"
        "2.0.1 风电场 wind farm\n"
        "定义一。\n"
        "2.0.2 风电机组 wind turbine\n"
        "定义二。\n",
        encoding="utf-8",
    )
    drafts = TxtTranslateStrategy().extract(src)
    assert len(drafts) >= 3
    assert any("2.0.1" in d.source_text for d in drafts)
    assert any("2.0.2" in d.source_text for d in drafts)


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
