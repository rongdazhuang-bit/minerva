"""Layout selection: rule mapping and hybrid LLM selection."""

from __future__ import annotations

from app.core.log import get_logger
import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.agent.skills.ppt.pptmaker.constants import AI_MIN_CONFIDENCE

log = get_logger(__name__)


def layout_summary(layout_index: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a compact layout list for LLM layout selection prompts."""

    return [
        {
            "layoutIndex": layout["layoutIndex"],
            "name": layout["name"],
            "description": layout.get("description", ""),
            "bestFor": layout.get("bestFor", []),
            "avoidFor": layout.get("avoidFor", []),
            "selectionRules": layout.get("selectionRules", ""),
            "contentSignals": layout.get("contentSignals", {}),
            "placeholders": [
                {
                    "idx": ph.get("idx"),
                    "type": ph.get("type"),
                    "label": ph.get("label"),
                }
                for ph in layout.get("placeholders", [])
            ],
        }
        for layout in layout_index
    ]


def layout_names(layout_index: list[dict[str, Any]]) -> set[str]:
    """Return the set of layout names in the index."""

    return {layout["name"] for layout in layout_index}


def find_first_layout(
    layout_index: list[dict[str, Any]],
    names: list[str],
    layout_types: list[str],
) -> str | None:
    """Find the first matching layout by name or contentSignals.layoutType."""

    available = layout_names(layout_index)
    for name in names:
        if name in available:
            return name
    for layout_type in layout_types:
        for layout in layout_index:
            if layout.get("contentSignals", {}).get("layoutType") == layout_type:
                return layout["name"]
    return None


def select_layout_by_rule(slide_spec: dict[str, Any], layout_index: list[dict[str, Any]]) -> str:
    """Pick a layout name using deterministic content signals."""

    if slide_spec.get("pageType") == "cover":
        selected = find_first_layout(layout_index, ["标题幻灯片"], ["cover"])
        return selected or "标题幻灯片"

    if slide_spec.get("keyNumbers"):
        metric_count = len(slide_spec.get("keyNumbers", []))
        if metric_count == 3:
            selected = find_first_layout(
                layout_index,
                ["大数字展示-三项居中", "大数字展示"],
                ["metrics_three_center", "metrics"],
            )
        elif metric_count == 4:
            selected = find_first_layout(
                layout_index,
                ["大数字展示-横向四项", "大数字展示-田字四项", "大数字展示"],
                ["metrics_horizontal", "metrics_grid", "metrics"],
            )
        else:
            selected = find_first_layout(
                layout_index,
                ["大数字展示-横向四项", "大数字展示"],
                ["metrics_horizontal", "metrics"],
            )
        return selected or "大数字展示"

    if slide_spec.get("hasImage"):
        image_count = len(slide_spec.get("images", []))
        if image_count == 1:
            return (
                find_first_layout(
                    layout_index,
                    ["左图右文-左右均分", "左图右文"],
                    ["image_left_text_right"],
                )
                or "左图右文"
            )
        if image_count == 2:
            return (
                find_first_layout(
                    layout_index,
                    ["两图并排-带说明", "两图并排"],
                    ["two_images_with_captions", "two_images"],
                )
                or "两图并排"
            )
        if image_count == 3:
            return (
                find_first_layout(
                    layout_index,
                    ["三图横排-带说明", "三图横排"],
                    ["three_images_with_captions", "three_images"],
                )
                or "三图横排"
            )
        if image_count == 4:
            return (
                find_first_layout(
                    layout_index,
                    ["四图宫格-带说明", "四图宫格"],
                    ["four_images_grid_with_captions", "four_images"],
                )
                or "四图宫格"
            )
        if image_count == 5:
            return find_first_layout(layout_index, ["五图版式-均等上三下二"], ["five_images"]) or "左图右文"
        if image_count == 6:
            return find_first_layout(layout_index, ["六图宫格-3x2带说明"], ["six_images_grid"]) or "左图右文"
        return (
            find_first_layout(
                layout_index,
                ["左图右文-左右均分", "左图右文"],
                ["image_left_text_right"],
            )
            or "左图右文"
        )

    item_count = len(slide_spec.get("items", []))
    if item_count == 3:
        return find_first_layout(layout_index, ["三列并列-等宽横排", "三列并列"], ["three_columns"]) or "三列并列"
    if item_count == 4:
        return find_first_layout(layout_index, ["四宫格-田字分布", "四宫格"], ["four_grid"]) or "四宫格"
    if item_count == 6:
        return (
            find_first_layout(
                layout_index,
                ["要点列表-双列六条", "六列并列"],
                ["bullet_list_two_columns", "six_columns"],
            )
            or "要点列表"
        )
    if item_count == 2:
        return (
            find_first_layout(
                layout_index,
                ["二列对比-左右等分", "自定义版式"],
                ["two_columns_compare", "two_columns"],
            )
            or "自定义版式"
        )
    if item_count == 1:
        item = slide_spec.get("items", [{}])[0]
        if item.get("body") and not item.get("title"):
            return (
                find_first_layout(
                    layout_index,
                    ["单段叙述-通栏正文", "单段叙述"],
                    ["single_paragraph_full", "single_paragraph"],
                )
                or "单段叙述"
            )
        return find_first_layout(layout_index, ["引言金句-居中", "引言金句"], ["quote_center", "quote"]) or "引言金句"
    if slide_spec.get("body"):
        return (
            find_first_layout(
                layout_index,
                ["单段叙述-通栏正文", "单段叙述"],
                ["single_paragraph_full", "single_paragraph"],
            )
            or "单段叙述"
        )
    return (
        find_first_layout(
            layout_index,
            ["要点列表-纵向六条", "要点列表"],
            ["bullet_list_vertical", "bullet_list"],
        )
        or "要点列表"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse JSON from model output, stripping optional markdown fences."""

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def layout_selection_prompt(slide_spec: dict[str, Any], layout_index: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the user prompt payload for LLM layout selection."""

    return {
        "task": "根据单页大纲和可用 PPT Layout 索引，选择最适合的一个 Layout。只返回 JSON。",
        "outputSchema": {
            "selectedLayoutName": "必须是 availableLayouts 中的 name",
            "confidence": "0 到 1 的数字",
            "reason": "简短中文理由",
        },
        "rules": [
            "不要选择不存在的 Layout 名称。",
            "优先匹配页面类型、图片数量、要点数量、数字指标、正文长短。",
            "如果多个变体都合适，选择信息承载最贴合的一种。",
            "不要负责填充内容，只选择版式。",
        ],
        "slide": slide_spec,
        "availableLayouts": layout_summary(layout_index),
    }


async def call_llm_layout_selector(
    slide_spec: dict[str, Any],
    layout_index: list[dict[str, Any]],
    chat_model: BaseChatModel,
) -> dict[str, Any] | None:
    """Ask the run chat model to pick a layout; return parsed JSON or None."""

    prompt = layout_selection_prompt(slide_spec, layout_index)
    try:
        response = await chat_model.ainvoke(
            [HumanMessage(content=json.dumps(prompt, ensure_ascii=False))]
        )
    except Exception as exc:
        log.warning("LLM layout selection failed: {}", exc)
        return None

    text = response.content
    if isinstance(text, list):
        parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in text]
        text = "\n".join(parts)
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return extract_json_object(text)
    except (json.JSONDecodeError, TypeError) as exc:
        log.warning("LLM layout selection invalid JSON: {}", exc)
        return None


async def select_layout_name(
    slide_spec: dict[str, Any],
    layout_index: list[dict[str, Any]],
    *,
    layout_mode: str,
    chat_model: BaseChatModel | None,
) -> tuple[str, str, str]:
    """Select layout name; return (name, selectionMethod, reason)."""

    rule_layout = select_layout_by_rule(slide_spec, layout_index)
    if layout_mode == "rule":
        return rule_layout, "rule", "规则映射"

    if layout_mode == "hybrid" and chat_model is not None:
        ai_result = await call_llm_layout_selector(slide_spec, layout_index, chat_model)
        if ai_result:
            selected = ai_result.get("selectedLayoutName", "")
            confidence = float(ai_result.get("confidence", 0) or 0)
            if selected in layout_names(layout_index) and confidence >= AI_MIN_CONFIDENCE:
                return selected, "ai", str(ai_result.get("reason", ""))
            log.info(
                "AI layout rejected: selected=%r confidence={}",
                selected,
                confidence,
            )
        return rule_layout, "rule_fallback", "混合模式下回退到规则映射"

    return rule_layout, "rule", "规则映射"
