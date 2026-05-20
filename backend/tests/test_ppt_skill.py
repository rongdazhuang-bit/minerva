"""Tests for PPT maker skill (normalize, rule layout selection, generation)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.agent.skills.ppt.pptmaker.generate import generate_presentation
from app.agent.skills.ppt.pptmaker.layout_select import select_layout_by_rule
from app.agent.skills.ppt.pptmaker.normalize import expand_outline_with_meta, normalize_slide
from app.agent.skills.ppt.pptmaker.constants import DEFAULT_LAYOUT_INDEX_PATH

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ppt_test_outline.json"


@pytest.fixture
def layout_index() -> list[dict]:
    """Load bundled layout index."""

    return json.loads(DEFAULT_LAYOUT_INDEX_PATH.read_text(encoding="utf-8"))


def test_normalize_slide_from_content_lines() -> None:
    """Multiline content splits into title/body items."""

    spec = normalize_slide(
        {
            "title": "三大优势",
            "content": "技术创新：持续研发\n生态合作：300+ 伙伴\n安全保障：合规管控",
        }
    )
    assert len(spec["items"]) == 3
    assert spec["items"][0]["title"] == "技术创新"


def test_normalize_slide_metrics() -> None:
    """Numeric lines become keyNumbers."""

    spec = normalize_slide(
        {
            "pageTitle": "成果",
            "items": [
                {"title": "19", "body": "Layout 数量"},
                {"title": "15", "body": "新增版式"},
                {"title": "100%", "body": "占位符化"},
            ],
        }
    )
    assert len(spec["keyNumbers"]) == 3


def test_select_layout_by_rule_three_items(layout_index: list[dict]) -> None:
    """Three items map to three-column layout."""

    slide = normalize_slide(
        {
            "pageTitle": "三大优势",
            "items": [
                {"title": "技术创新", "body": "持续研发"},
                {"title": "生态合作", "body": "300+ 伙伴"},
                {"title": "安全保障", "body": "合规管控"},
            ],
        }
    )
    name = select_layout_by_rule(slide, layout_index)
    assert "三列" in name


def test_select_layout_by_rule_six_items(layout_index: list[dict]) -> None:
    """Six items map to bullet list two-column layout."""

    slide = {
        "pageTitle": "指标说明",
        "items": [{"title": f"t{i}", "body": f"b{i}"} for i in range(6)],
        "keyNumbers": [],
        "body": "",
        "hasImage": False,
        "images": [],
    }
    name = select_layout_by_rule(slide, layout_index)
    assert "六" in name or "要点" in name


@pytest.mark.asyncio
async def test_generate_ppt_rule_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end generation with rule layout mode writes a pptx file."""

    from app.config import settings

    ws_id = uuid.uuid4()
    root = tmp_path / "workspaces" / str(ws_id)
    root.mkdir(parents=True)
    monkeypatch.setattr(settings, "agent_files_root", str(tmp_path))

    raw_slides = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    outline = {"slides": raw_slides}

    result = await generate_presentation(
        outline,
        workspace_id=ws_id,
        output_path="output/test.pptx",
        layout_mode="rule",
        chat_model=None,
    )

    assert result["ok"] is True
    out = root / "output" / "test.pptx"
    assert out.is_file()
    assert out.stat().st_size > 1000
    assert len(result["pages"]) == len(raw_slides)


def test_expand_outline_with_meta() -> None:
    """Meta prepends a cover slide."""

    specs = expand_outline_with_meta(
        {
            "meta": {"title": "主标题", "subtitle": "副标题"},
            "slides": [{"pageTitle": "正文"}],
        }
    )
    assert specs[0].get("pageType") == "cover"
    assert specs[0]["pageTitle"] == "主标题"
    assert len(specs) == 2
