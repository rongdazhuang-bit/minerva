"""Normalize raw slide dicts into canonical slide_spec structures."""

from __future__ import annotations

import re
from typing import Any

from app.agent.skills.ppt.pptmaker.constants import TEMPLATE_PLACEHOLDER_LITERALS

_TOC_TITLES = frozenset({"目录", "目 录", "Table of Contents", "TOC", "Contents"})

def _is_template_literal(text: str) -> bool:
    """Return whether text is a schema/template example literal, not real content."""

    stripped = text.strip()
    return stripped in TEMPLATE_PLACEHOLDER_LITERALS


def _is_toc_slide(raw_slide: dict[str, Any]) -> bool:
    """Detect table-of-contents slides from pageType or title."""

    page_type = str(raw_slide.get("pageType", "")).strip().lower()
    if page_type in {"toc", "目录", "table_of_contents"}:
        return True
    title = str(raw_slide.get("pageTitle", raw_slide.get("title", ""))).strip()
    return title in _TOC_TITLES


def _sanitize_field(text: str) -> str:
    """Drop template example literals so they are not written into the deck."""

    stripped = str(text).strip()
    if _is_template_literal(stripped):
        return ""
    return stripped


def split_content_lines(content: str) -> list[str]:
    """Split multiline content into non-empty stripped lines."""

    return [line.strip() for line in content.splitlines() if line.strip()]


def split_title_body(line: str) -> tuple[str, str] | None:
    """Parse a single line into title and body when a separator is present."""

    for sep in ("：", ":", " - ", " — ", "，", ","):
        if sep in line:
            title, body = line.split(sep, 1)
            title = title.strip(" -—\t")
            body = body.strip()
            if title and body and len(title) <= 20:
                return title, body
    return None


def parse_metric_line(line: str) -> dict[str, str] | None:
    """Parse a metric line like ``19：说明`` into number/label/desc."""

    match = re.match(r"^([0-9]+(?:\.[0-9]+)?%?|[0-9]+[+＋]?)\s*(.*)$", line.strip())
    if not match:
        return None
    number = match.group(1)
    rest = match.group(2).strip(" ：:-")
    if not rest:
        return None
    parts = re.split(r"[，,。；;]", rest, maxsplit=1)
    label = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ""
    return {"number": number, "label": label, "desc": desc}


def looks_like_number(value: str) -> bool:
    """Return whether ``value`` looks like a numeric metric."""

    return bool(re.match(r"^[0-9]+(?:\.[0-9]+)?%?|[0-9]+[+＋]?$", value.strip()))


def _coerce_text_item(raw: Any, *, title_only: bool = False) -> dict[str, str] | None:
    """Normalize one outline item (dict or plain string) to title/body."""

    if isinstance(raw, dict):
        title = _sanitize_field(str(raw.get("title", "")))
        body = _sanitize_field(str(raw.get("body", "")))
        if title_only and body and not title:
            title, body = body, ""
        if title or body:
            return {"title": title, "body": body}
        return None
    if isinstance(raw, str):
        text = _sanitize_field(raw)
        if not text:
            return None
        if title_only:
            return {"title": text, "body": ""}
        parsed = split_title_body(text)
        if parsed:
            title, body = parsed
            if _is_template_literal(title) or _is_template_literal(body):
                return None
            return {"title": title, "body": body}
        return {"title": "", "body": text}
    return None


def _coerce_metric(raw: Any) -> dict[str, str] | None:
    """Normalize one keyNumber entry to number/label/desc."""

    if isinstance(raw, dict):
        number = _sanitize_field(str(raw.get("number", "")))
        label = _sanitize_field(str(raw.get("label", "")))
        desc = _sanitize_field(str(raw.get("desc", "")))
        if number or label:
            return {"number": number, "label": label, "desc": desc}
        return None
    if isinstance(raw, str):
        return parse_metric_line(raw.strip())
    return None


def _coerce_image(raw: Any) -> dict[str, str] | None:
    """Normalize one image entry to path/caption."""

    if isinstance(raw, dict):
        path = str(raw.get("path", "")).strip()
        if path:
            return {
                "path": path,
                "caption": str(raw.get("caption", "")).strip(),
            }
        return None
    if isinstance(raw, str):
        path = raw.strip()
        if path:
            return {"path": path, "caption": ""}
    return None


def _coerce_items(raw_items: Any, *, title_only: bool = False) -> list[dict[str, str]]:
    """Normalize a list of outline items."""

    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for raw in raw_items:
        item = _coerce_text_item(raw, title_only=title_only)
        if item:
            items.append(item)
    return items


def _coerce_key_numbers(raw: Any) -> list[dict[str, str]]:
    """Normalize a list of metric entries."""

    if not isinstance(raw, list):
        return []
    metrics: list[dict[str, str]] = []
    for entry in raw:
        metric = _coerce_metric(entry)
        if metric:
            metrics.append(metric)
    return metrics


def _coerce_images(raw: Any) -> list[dict[str, str]]:
    """Normalize a list of image entries."""

    if not isinstance(raw, list):
        return []
    images: list[dict[str, str]] = []
    for entry in raw:
        image = _coerce_image(entry)
        if image:
            images.append(image)
    return images


def metric_from_item(item: dict[str, Any]) -> dict[str, str] | None:
    """Extract a metric dict from a title/body item pair."""

    title = str(item.get("title", "")).strip()
    body = str(item.get("body", "")).strip()
    if title and looks_like_number(title):
        body_parts = re.split(r"[，,。；;]", body, maxsplit=1)
        label = body_parts[0].strip()
        desc = body_parts[1].strip() if len(body_parts) > 1 else ""
        return {"number": title, "label": label, "desc": desc}
    if body and looks_like_number(body):
        return {"number": body, "label": title, "desc": ""}
    if not title and body:
        return parse_metric_line(body)
    return None


def normalize_slide(raw_slide: dict[str, Any]) -> dict[str, Any]:
    """Convert one raw outline slide into a canonical slide_spec dict."""

    if raw_slide.get("pageType") == "cover":
        return {
            "pageTitle": str(raw_slide.get("pageTitle", raw_slide.get("title", ""))).strip(),
            "subtitle": str(raw_slide.get("subtitle", "")).strip(),
            "items": [],
            "body": "",
            "hasImage": False,
            "images": [],
            "keyNumbers": [],
            "pageType": "cover",
        }

    if "items" in raw_slide:
        page_title = _sanitize_field(str(raw_slide.get("pageTitle", raw_slide.get("title", ""))))
        title_only_items = _is_toc_slide(raw_slide)
        images = _coerce_images(raw_slide.get("images", []))
        items = _coerce_items(raw_slide.get("items", []), title_only=title_only_items)

        if raw_slide.get("keyNumbers"):
            key_numbers = _coerce_key_numbers(raw_slide.get("keyNumbers", []))
        else:
            metrics = [metric_from_item(item) for item in items]
            key_numbers = metrics if items and all(metric is not None for metric in metrics) else []

        body = _sanitize_field(str(raw_slide.get("body", "")))
        if not body and len(items) == 1 and items[0].get("body") and not items[0].get("title"):
            body = items[0]["body"]

        page_type = "toc" if title_only_items else raw_slide.get("pageType")

        return {
            "pageTitle": page_title,
            "subtitle": _sanitize_field(str(raw_slide.get("subtitle", ""))),
            "items": [] if key_numbers else items,
            "body": body,
            "hasImage": bool(raw_slide.get("hasImage", bool(images))),
            "images": images,
            "keyNumbers": key_numbers,
            "pageType": page_type,
        }

    if any(key in raw_slide for key in ("pageTitle", "keyNumbers", "body", "hasImage")):
        normalized = dict(raw_slide)
        normalized.setdefault("pageTitle", normalized.get("title", ""))
        normalized["items"] = _coerce_items(
            normalized.get("items", []),
            title_only=_is_toc_slide(normalized),
        )
        if _is_toc_slide(normalized):
            normalized["pageType"] = "toc"
        normalized["keyNumbers"] = _coerce_key_numbers(normalized.get("keyNumbers", []))
        normalized["images"] = _coerce_images(normalized.get("images", []))
        normalized.setdefault("hasImage", bool(normalized.get("images")))
        normalized.setdefault("subtitle", "")
        return normalized

    title = raw_slide.get("title", "")
    content = raw_slide.get("content", "")
    lines = split_content_lines(str(content))
    images = _coerce_images(raw_slide.get("images", []))
    has_image = bool(images)
    page_title = _sanitize_field(str(title))

    if _is_toc_slide({"pageTitle": page_title, "pageType": raw_slide.get("pageType")}) and lines:
        return {
            "pageTitle": page_title,
            "subtitle": "",
            "items": [{"title": _sanitize_field(line), "body": ""} for line in lines if not _is_template_literal(line)],
            "body": "",
            "hasImage": has_image,
            "images": images,
            "keyNumbers": [],
            "pageType": "toc",
        }

    metrics = [parse_metric_line(line) for line in lines]
    if lines and all(metric is not None for metric in metrics):
        return {
            "pageTitle": str(title).strip(),
            "subtitle": "",
            "items": [],
            "body": "",
            "hasImage": has_image,
            "images": images,
            "keyNumbers": metrics,
        }

    item_pairs = [split_title_body(line) for line in lines]
    if len(lines) > 1 and all(item is not None for item in item_pairs):
        return {
            "pageTitle": str(title).strip(),
            "subtitle": "",
            "items": [{"title": item[0], "body": item[1]} for item in item_pairs if item],
            "body": "",
            "hasImage": has_image,
            "images": images,
            "keyNumbers": [],
        }

    return {
        "pageTitle": str(title).strip(),
        "subtitle": "",
        "items": [{"body": str(content).strip()}] if str(content).strip() else [],
        "body": str(content).strip(),
        "hasImage": has_image,
        "images": images,
        "keyNumbers": [],
    }


def slide_has_content(slide_spec: dict[str, Any]) -> bool:
    """Return whether a normalized slide carries fillable content."""

    if slide_spec.get("pageType") == "cover":
        return bool(slide_spec.get("pageTitle") or slide_spec.get("subtitle"))
    if slide_spec.get("pageTitle") or slide_spec.get("subtitle") or slide_spec.get("body"):
        return True
    if slide_spec.get("items") or slide_spec.get("keyNumbers") or slide_spec.get("images"):
        return True
    return False


def expand_outline_with_meta(outline: dict[str, Any]) -> list[dict[str, Any]]:
    """Prepend a cover slide when ``meta`` is present and normalize all slides."""

    slides_raw = outline.get("slides", [])
    if not isinstance(slides_raw, list):
        raise ValueError("outline.slides must be a list")

    slide_specs: list[dict[str, Any]] = []
    meta = outline.get("meta")
    has_meta_cover = isinstance(meta, dict) and (meta.get("title") or meta.get("subtitle"))
    if has_meta_cover:
        slide_specs.append(
            normalize_slide(
                {
                    "pageType": "cover",
                    "pageTitle": str(meta.get("title", "")).strip(),
                    "subtitle": str(meta.get("subtitle", "")).strip(),
                }
            )
        )

    for raw in slides_raw:
        if not isinstance(raw, dict):
            raise ValueError("each slide must be an object")
        if has_meta_cover and raw.get("pageType") == "cover":
            continue
        normalized = normalize_slide(raw)
        if slide_has_content(normalized):
            slide_specs.append(normalized)
    if not slide_specs:
        raise ValueError("outline has no slides with content after normalization")
    return slide_specs
