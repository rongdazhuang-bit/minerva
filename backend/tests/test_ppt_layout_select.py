"""Tests for pptmaker.layout_select rule mapping."""

from __future__ import annotations

import json
from pathlib import Path

from app.agent.skills.ppt.pptmaker.layout_select import select_layout_by_rule

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_LAYOUT_INDEX = _BACKEND_ROOT / "app/agent/skills/ppt/assets/layout_index.json"


def _load_index() -> list[dict]:
    """Load the bundled PPT layout index JSON."""

    return json.loads(_LAYOUT_INDEX.read_text(encoding="utf-8"))


def test_rule_selects_three_column_for_three_items() -> None:
    """Three items map to a three-column layout name."""

    layout_index = _load_index()
    slide_spec = {
        "pageTitle": "三大优势",
        "items": [
            {"title": "a", "body": "1"},
            {"title": "b", "body": "2"},
            {"title": "c", "body": "3"},
        ],
    }
    name = select_layout_by_rule(slide_spec, layout_index)
    assert "三列" in name


def test_rule_selects_cover_for_page_type() -> None:
    """Cover page type selects title slide layout."""

    layout_index = _load_index()
    name = select_layout_by_rule({"pageType": "cover", "pageTitle": "封面"}, layout_index)
    assert name == "标题幻灯片"


def test_layout_index_has_geometry_on_placeholders() -> None:
    """Placeholder entries include geometry width hints after extraction."""

    layout_index = _load_index()
    first_ph = layout_index[0]["placeholders"][0]
    assert "geometry" in first_ph
    assert first_ph["geometry"]["widthPt"] > 0


def test_rule_selects_toc_layout_for_page_type() -> None:
    """TOC pages prefer horizontal bullet list for short chapter lists."""

    layout_index = _load_index()
    name = select_layout_by_rule(
        {
            "pageType": "toc",
            "pageTitle": "目录",
            "items": [{"title": "A", "body": ""}, {"title": "B", "body": ""}],
        },
        layout_index,
    )
    assert "要点列表" in name


def test_layout_index_has_capacity_hints() -> None:
    """Each layout entry includes aggregated capacity hints."""

    layout_index = _load_index()
    entry = layout_index[0]
    assert "capacityHints" in entry
    hints = entry["capacityHints"]
    assert "byLabel" in hints
    assert hints["byLabel"]["title"]["capacityUnits"] > 0


def test_rule_prefers_full_width_paragraph_for_long_body() -> None:
    """Long single-paragraph content selects the full-width narrative layout."""

    layout_index = _load_index()
    long_body = "这是一段用于测试排版容量的长正文。" * 8
    name = select_layout_by_rule(
        {"pageTitle": "背景", "body": long_body},
        layout_index,
    )
    assert name == "单段叙述-通栏正文"
