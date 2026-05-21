"""Tests for plain-text segmentation used by txt/md translation strategies."""

from app.translate.service.text_segmentation import split_plain_text_into_segments


def test_split_numbered_subclauses_without_blank_lines() -> None:
    """Lines like ``2.0.1`` should become separate segments even without blank lines."""

    text = (
        "2 术语和定义\n"
        "下列术语适用于本文件。\n"
        "2.0.1\n"
        "风电场 wind farm\n"
        "由多台机组组成。\n"
        "2.0.2\n"
        "风电机组 wind turbine\n"
        "单机或机组群。\n"
        "3 风电场接入\n"
        "一般要求。\n"
    )
    parts = split_plain_text_into_segments(text)
    assert len(parts) >= 4
    assert any("2.0.1" in p for p in parts)
    assert any("2.0.2" in p for p in parts)
    assert any(p.strip().startswith("3 ") for p in parts)


def test_split_blank_lines_still_works() -> None:
    """Blank-line paragraphs remain separate segments."""

    text = "hello\n\nworld\n"
    parts = split_plain_text_into_segments(text)
    assert parts == ["hello", "world"]


def test_split_oversized_paragraph_by_lines() -> None:
    """Very long blocks are chunked under the character budget."""

    line = "x" * 100
    text = "\n".join([line] * 80)
    parts = split_plain_text_into_segments(text, max_chars=500)
    assert len(parts) > 1
    assert all(len(p) <= 500 for p in parts)
