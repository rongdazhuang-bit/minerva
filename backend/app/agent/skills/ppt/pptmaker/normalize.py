"""Normalize raw slide dicts into canonical slide_spec structures."""

from __future__ import annotations

import re
from typing import Any


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
        page_title = raw_slide.get("pageTitle", raw_slide.get("title", ""))
        images = raw_slide.get("images", [])
        items = [
            {
                "title": str(item.get("title", "")).strip(),
                "body": str(item.get("body", "")).strip(),
            }
            for item in raw_slide.get("items", [])
            if str(item.get("title", "")).strip() or str(item.get("body", "")).strip()
        ]

        if raw_slide.get("keyNumbers"):
            key_numbers = raw_slide.get("keyNumbers", [])
        else:
            metrics = [metric_from_item(item) for item in items]
            key_numbers = metrics if items and all(metric is not None for metric in metrics) else []

        body = str(raw_slide.get("body", "")).strip()
        if not body and len(items) == 1 and items[0].get("body") and not items[0].get("title"):
            body = items[0]["body"]

        return {
            "pageTitle": str(page_title).strip(),
            "subtitle": str(raw_slide.get("subtitle", "")).strip(),
            "items": [] if key_numbers else items,
            "body": body,
            "hasImage": bool(raw_slide.get("hasImage", bool(images))),
            "images": images,
            "keyNumbers": key_numbers,
        }

    if any(key in raw_slide for key in ("pageTitle", "keyNumbers", "body", "hasImage")):
        normalized = dict(raw_slide)
        normalized.setdefault("pageTitle", normalized.get("title", ""))
        normalized.setdefault("items", [])
        normalized.setdefault("keyNumbers", [])
        normalized.setdefault("hasImage", bool(normalized.get("images")))
        normalized.setdefault("subtitle", "")
        return normalized

    title = raw_slide.get("title", "")
    content = raw_slide.get("content", "")
    lines = split_content_lines(str(content))
    images = raw_slide.get("images", [])
    has_image = bool(images)

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


def expand_outline_with_meta(outline: dict[str, Any]) -> list[dict[str, Any]]:
    """Prepend a cover slide when ``meta`` is present and normalize all slides."""

    slides_raw = outline.get("slides", [])
    if not isinstance(slides_raw, list):
        raise ValueError("outline.slides must be a list")

    slide_specs: list[dict[str, Any]] = []
    meta = outline.get("meta")
    if isinstance(meta, dict) and (meta.get("title") or meta.get("subtitle")):
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
        slide_specs.append(normalize_slide(raw))
    return slide_specs
