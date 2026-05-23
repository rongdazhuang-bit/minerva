"""Tests for Markdown translation strategy behavior."""

from pathlib import Path

from app.translate.domain.dto import SegmentRecord
from app.translate.service.strategies.md_strategy import MdTranslateStrategy


def test_markdown_fenced_code_is_skip_translate(tmp_path: Path) -> None:
    """Keep fenced code blocks unchanged while translating normal Markdown text."""
    source = tmp_path / "source.md"
    output = tmp_path / "output.md"
    source.write_text(
        "# Title\n\nTranslate me.\n\n```python\nprint('do not translate')\n```\n",
        encoding="utf-8",
    )

    strategy = MdTranslateStrategy()
    drafts = strategy.extract(source)

    code = next(d for d in drafts if "print(" in d.source_text)
    assert code.anchor_json is not None
    assert code.anchor_json["skip_translate"] is True
    assert code.anchor_json["label"] == "code"

    records = [
        SegmentRecord(
            seq=d.seq,
            source_text=d.source_text,
            translated_text=(
                d.source_text
                if d.anchor_json and d.anchor_json.get("skip_translate")
                else "译文"
            ),
            anchor_json=d.anchor_json,
        )
        for d in drafts
    ]
    strategy.assemble(records, source, output)

    written = output.read_text(encoding="utf-8")
    assert "```python\nprint('do not translate')\n```" in written
    assert "译文" in written
