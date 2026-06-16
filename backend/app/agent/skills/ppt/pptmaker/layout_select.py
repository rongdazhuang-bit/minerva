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

_CJK_RATIO = 1.0
_LATIN_RATIO = 0.55


def _visual_length(text: str) -> float:
    """Return weighted visual length treating CJK wider than Latin."""

    total = 0.0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            total += _CJK_RATIO
        else:
            total += _LATIN_RATIO
    return total


def _slide_body_lengths(slide_spec: dict[str, Any]) -> list[float]:
    """Collect visual lengths of body text blocks on one slide."""

    lengths: list[float] = []
    body = str(slide_spec.get("body", "")).strip()
    if body:
        lengths.append(_visual_length(body))
    for item in slide_spec.get("items", []):
        if isinstance(item, dict):
            text = str(item.get("body", "")).strip()
            if text:
                lengths.append(_visual_length(text))
        elif isinstance(item, str) and item.strip():
            lengths.append(_visual_length(item.strip()))
    return lengths


def _slide_title_length(slide_spec: dict[str, Any]) -> float:
    """Return visual length of the page title."""

    return _visual_length(str(slide_spec.get("pageTitle", "")).strip())


def _slide_item_count(slide_spec: dict[str, Any]) -> int:
    """Count list items when present, otherwise treat body as one block."""

    items = slide_spec.get("items") or []
    if items:
        return len(items)
    if str(slide_spec.get("body", "")).strip():
        return 1
    return 0


def layouts_matching(
    layout_index: list[dict[str, Any]],
    *,
    names: list[str] | None = None,
    name_prefix: str | None = None,
    layout_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return layout entries matching explicit names, prefix, or layoutType."""

    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for layout in layout_index:
        layout_name = layout["name"]
        if layout_name in seen:
            continue
        if names and layout_name in names:
            matched.append(layout)
            seen.add(layout_name)
            continue
        if name_prefix and layout_name.startswith(name_prefix):
            matched.append(layout)
            seen.add(layout_name)
            continue
        layout_type = layout.get("contentSignals", {}).get("layoutType", "")
        if layout_types and layout_type in layout_types:
            matched.append(layout)
            seen.add(layout_name)
    return matched


def score_layout_fit(slide_spec: dict[str, Any], layout_entry: dict[str, Any]) -> float:
    """Score how well a layout variant fits slide content and capacity."""

    signals = layout_entry.get("contentSignals", {})
    hints = layout_entry.get("capacityHints", {})
    score = 0.0

    item_count = _slide_item_count(slide_spec)
    max_items = int(signals.get("maxItems") or 0)
    if max_items:
        if item_count <= max_items:
            score += 20.0 - abs(max_items - item_count) * 2.0
        else:
            score -= 40.0 + (item_count - max_items) * 10.0

    body_lengths = _slide_body_lengths(slide_spec)
    min_body_capacity = hints.get("minBodyCapacity")
    if body_lengths and min_body_capacity:
        longest = max(body_lengths)
        if longest <= float(min_body_capacity) * 1.05:
            score += 15.0
        else:
            score -= (longest - float(min_body_capacity)) * 0.5

    min_title_capacity = hints.get("minTitleCapacity")
    title_length = _slide_title_length(slide_spec)
    if title_length and min_title_capacity:
        if title_length <= float(min_title_capacity) * 1.05:
            score += 5.0
        else:
            score -= (title_length - float(min_title_capacity)) * 0.3

    image_count = len(slide_spec.get("images") or [])
    signal_image_count = int(signals.get("imageCount") or 0)
    if slide_spec.get("hasImage") or image_count:
        if signal_image_count == image_count:
            score += 12.0
        elif signal_image_count > 0:
            score -= abs(signal_image_count - image_count) * 8.0
    elif not signals.get("hasImage"):
        score += 3.0

    return score


def pick_best_layout(
    slide_spec: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    fallback: str,
) -> str:
    """Pick the highest-scoring layout name from candidates."""

    if not candidates:
        return fallback
    best = max(candidates, key=lambda entry: score_layout_fit(slide_spec, entry))
    return str(best["name"])


def pick_layout_variant(
    slide_spec: dict[str, Any],
    layout_index: list[dict[str, Any]],
    *,
    preferred_names: list[str],
    name_prefix: str | None = None,
    layout_types: list[str] | None = None,
    fallback: str,
) -> str:
    """Resolve the best matching variant among preferred names or prefix/type pool."""

    by_name = layouts_matching(layout_index, names=preferred_names)
    if by_name:
        return pick_best_layout(slide_spec, by_name, fallback=fallback)
    pool = layouts_matching(
        layout_index,
        name_prefix=name_prefix,
        layout_types=layout_types,
    )
    return pick_best_layout(slide_spec, pool, fallback=fallback)


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
            "capacityHints": layout.get("capacityHints", {}),
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
    """Pick a layout name using deterministic content signals and capacity scoring."""

    if slide_spec.get("pageType") == "cover":
        selected = find_first_layout(layout_index, ["标题幻灯片"], ["cover"])
        return selected or "标题幻灯片"

    if slide_spec.get("pageType") == "toc":
        item_count = len(slide_spec.get("items", []))
        if item_count <= 4:
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=["要点列表-横向四项", "要点列表-纵向六条", "要点列表"],
                name_prefix="要点列表",
                layout_types=["bullet_list_horizontal", "bullet_list_vertical", "bullet_list"],
                fallback="要点列表-横向四项",
            )
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["要点列表-纵向六条", "要点列表-双列六条", "要点列表"],
            name_prefix="要点列表",
            layout_types=["bullet_list_vertical", "bullet_list_two_columns", "bullet_list"],
            fallback="要点列表-纵向六条",
        )

    if slide_spec.get("keyNumbers"):
        metric_count = len(slide_spec.get("keyNumbers", []))
        if metric_count == 3:
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=["大数字展示-三项居中", "大数字展示"],
                layout_types=["metrics_three_center", "metrics"],
                fallback="大数字展示-三项居中",
            )
        if metric_count == 4:
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=["大数字展示-横向四项", "大数字展示-田字四项", "大数字展示"],
                layout_types=["metrics_horizontal", "metrics_grid", "metrics"],
                fallback="大数字展示-横向四项",
            )
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["大数字展示-横向四项", "大数字展示"],
            layout_types=["metrics_horizontal", "metrics"],
            fallback="大数字展示-横向四项",
        )

    if slide_spec.get("hasImage"):
        image_count = len(slide_spec.get("images", []))
        if image_count == 1:
            body_lengths = _slide_body_lengths(slide_spec)
            long_text = body_lengths and max(body_lengths) > 80
            preferred = (
                ["左图右文-小图大文", "左图右文-左右均分", "左图右文"]
                if long_text
                else ["左图右文-左右均分", "左图右文-小图大文", "左图右文"]
            )
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=preferred,
                name_prefix="左图右文",
                layout_types=["image_left_text_right_equal", "image_left_text_right_small_image", "image_left_text_right"],
                fallback="左图右文-左右均分",
            )
        if image_count == 2:
            has_captions = any(
                isinstance(image, dict) and str(image.get("caption", "")).strip()
                for image in slide_spec.get("images", [])
            )
            preferred = (
                ["两图并排-带说明", "两图并排-无说明", "两图并排"]
                if has_captions
                else ["两图并排-无说明", "两图并排-带说明", "两图并排"]
            )
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=preferred,
                name_prefix="两图并排",
                layout_types=["two_images_with_captions", "two_images"],
                fallback="两图并排-带说明",
            )
        if image_count == 3:
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=["三图横排-带说明", "三图横排-无说明", "三图横排"],
                name_prefix="三图横排",
                layout_types=["three_images_with_captions", "three_images"],
                fallback="三图横排-带说明",
            )
        if image_count == 4:
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=["四图宫格-带说明", "四图宫格-无说明", "四图宫格"],
                name_prefix="四图宫格",
                layout_types=["four_images_grid_with_captions", "four_images"],
                fallback="四图宫格-带说明",
            )
        if image_count == 5:
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=["五图版式-均等上三下二", "五图版式-主次左大", "五图版式"],
                name_prefix="五图版式",
                layout_types=["five_images", "five_images_hero"],
                fallback="五图版式-均等上三下二",
            )
        if image_count == 6:
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=["六图宫格-3x2带说明", "六图宫格-3x2无说明", "六图宫格"],
                name_prefix="六图宫格",
                layout_types=["six_images_grid_with_captions", "six_images_grid"],
                fallback="六图宫格-3x2带说明",
            )
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["左图右文-左右均分", "左图右文"],
            name_prefix="左图右文",
            layout_types=["image_left_text_right_equal", "image_left_text_right"],
            fallback="左图右文-左右均分",
        )

    item_count = len(slide_spec.get("items", []))
    if item_count == 3:
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["三列并列-等宽横排", "三列并列-上标题下正文", "三列并列-错落分布", "三列并列"],
            name_prefix="三列并列",
            layout_types=["three_columns_equal", "three_columns_stacked", "three_columns_staggered", "three_columns"],
            fallback="三列并列-等宽横排",
        )
    if item_count == 4:
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["四宫格-田字分布", "四宫格-横向四项", "四宫格-纵向四项", "四宫格"],
            name_prefix="四宫格",
            layout_types=["four_grid_tile", "four_grid_horizontal", "four_grid_vertical", "four_grid"],
            fallback="四宫格-田字分布",
        )
    if item_count == 6:
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["要点列表-双列六条", "六列并列", "要点列表-纵向六条"],
            name_prefix="要点列表",
            layout_types=["bullet_list_two_columns", "six_columns", "bullet_list_vertical", "bullet_list"],
            fallback="要点列表-双列六条",
        )
    if item_count == 2:
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["二列对比-左右等分", "二列对比-上下排列", "自定义版式"],
            name_prefix="二列对比",
            layout_types=["two_columns_compare_equal", "two_columns_compare_vertical", "two_columns", "two_columns_compare"],
            fallback="二列对比-左右等分",
        )
    if item_count == 1:
        item = slide_spec.get("items", [{}])[0]
        has_body_only = (
            isinstance(item, dict) and item.get("body") and not item.get("title")
        ) or (isinstance(item, str) and item.strip())
        if has_body_only:
            body_text = item.get("body", "") if isinstance(item, dict) else str(item)
            body_len = _visual_length(str(body_text))
            preferred = (
                ["单段叙述-通栏正文", "单段叙述-窄栏正文", "单段叙述"]
                if body_len > 60
                else ["单段叙述-窄栏正文", "单段叙述-通栏正文", "单段叙述"]
            )
            return pick_layout_variant(
                slide_spec,
                layout_index,
                preferred_names=preferred,
                name_prefix="单段叙述",
                layout_types=["single_paragraph_full", "single_paragraph_narrow", "single_paragraph"],
                fallback="单段叙述-通栏正文",
            )
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=["引言金句-居中", "引言金句-左对齐", "引言金句"],
            name_prefix="引言金句",
            layout_types=["quote_center", "quote_left", "quote"],
            fallback="引言金句-居中",
        )
    if slide_spec.get("body"):
        body_len = _visual_length(str(slide_spec.get("body", "")))
        preferred = (
            ["单段叙述-通栏正文", "单段叙述-窄栏正文", "单段叙述"]
            if body_len > 60
            else ["单段叙述-窄栏正文", "单段叙述-通栏正文", "单段叙述"]
        )
        return pick_layout_variant(
            slide_spec,
            layout_index,
            preferred_names=preferred,
            name_prefix="单段叙述",
            layout_types=["single_paragraph_full", "single_paragraph_narrow", "single_paragraph"],
            fallback="单段叙述-通栏正文",
        )
    return pick_layout_variant(
        slide_spec,
        layout_index,
        preferred_names=["要点列表-纵向六条", "要点列表-横向四项", "要点列表-双列六条", "要点列表"],
        name_prefix="要点列表",
        layout_types=["bullet_list_vertical", "bullet_list_horizontal", "bullet_list_two_columns", "bullet_list"],
        fallback="要点列表-纵向六条",
    )


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse JSON from model output, stripping optional markdown fences."""

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise TypeError("expected JSON object")
    return parsed


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
