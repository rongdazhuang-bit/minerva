"""Tests for pptmaker.normalize."""

from __future__ import annotations

from app.agent.skills.ppt.pptmaker.normalize import expand_outline_with_meta, normalize_slide


def test_normalize_slide_items_from_content_lines() -> None:
    """Multiline content splits into items."""

    spec = normalize_slide({"title": "页", "content": "A：正文a\nB：正文b"})
    assert len(spec["items"]) == 2
    assert spec["items"][0]["title"] == "A"


def test_expand_outline_with_meta_inserts_cover() -> None:
    """Meta block prepends a cover slide spec."""

    slides = expand_outline_with_meta(
        {"meta": {"title": "主标题", "subtitle": "副标题"}, "slides": [{"pageTitle": "正文"}]}
    )
    assert slides[0].get("pageType") == "cover"
    assert slides[0]["pageTitle"] == "主标题"
    assert len(slides) == 2


def test_normalize_slide_coerces_string_items() -> None:
    """String items from LLM output do not crash normalize."""

    spec = normalize_slide(
        {
            "pageTitle": "要点页",
            "items": ["要点一", "标题：正文"],
        }
    )
    assert len(spec["items"]) == 2
    assert spec["items"][0]["body"] == "要点一"
    assert spec["items"][1]["title"] == "标题"
    assert spec["items"][1]["body"] == "正文"


def test_normalize_slide_coerces_string_key_numbers_and_images() -> None:
    """String metrics and image paths are coerced to dicts."""

    spec = normalize_slide(
        {
            "pageTitle": "数据页",
            "keyNumbers": ["19：增长说明"],
            "images": ["/tmp/chart.png"],
            "hasImage": True,
        }
    )
    assert spec["keyNumbers"][0]["number"] == "19"
    assert spec["images"][0]["path"] == "/tmp/chart.png"


def test_expand_outline_with_meta_string_items() -> None:
    """Full outline with string items expands without AttributeError."""

    slides = expand_outline_with_meta(
        {
            "slides": [
                {
                    "pageTitle": "页1",
                    "items": ["A", "B：内容"],
                }
            ]
        }
    )
    assert len(slides) == 1
    assert slides[0]["items"][0]["body"] == "A"


def test_normalize_toc_uses_title_only_items() -> None:
    """TOC slides map string entries to item titles for list layouts."""

    spec = normalize_slide({"pageTitle": "目录", "items": ["第一章", "第二章"]})
    assert spec.get("pageType") == "toc"
    assert spec["items"][0]["title"] == "第一章"
    assert spec["items"][0]["body"] == ""


def test_normalize_strips_template_literals() -> None:
    """Schema example literals are removed instead of being written to pptx."""

    spec = normalize_slide(
        {
            "pageTitle": "目录",
            "items": [{"title": "要点标题", "body": "要点正文"}],
        }
    )
    assert spec["items"] == []


def test_expand_skips_duplicate_cover_and_empty_slides() -> None:
    """Meta cover is not duplicated and empty slides are dropped."""

    slides = expand_outline_with_meta(
        {
            "meta": {"title": "封面", "subtitle": "副标题"},
            "slides": [
                {"pageType": "cover", "pageTitle": "重复封面"},
                {"pageTitle": ""},
                {"pageTitle": "正文", "body": "有内容"},
            ],
        }
    )
    assert slides[0]["pageType"] == "cover"
    assert slides[0]["pageTitle"] == "封面"
    assert len(slides) == 2
    assert slides[1]["pageTitle"] == "正文"
