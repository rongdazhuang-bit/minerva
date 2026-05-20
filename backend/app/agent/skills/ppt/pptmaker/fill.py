"""Placeholder text values and picture insertion."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.presentation import Presentation
from pptx.slide import Slide


def value_for_label(slide_spec: dict[str, Any], label: str) -> str:
    """Map a placeholder label to text content from slide_spec."""

    if label in {"title", "toc_title"}:
        return slide_spec.get("pageTitle", "")

    if label == "subtitle":
        return slide_spec.get("subtitle", "")

    if label == "body":
        if slide_spec.get("body"):
            return slide_spec.get("body", "")
        items = slide_spec.get("items", [])
        if len(items) == 1:
            return items[0].get("body", "")
        return ""

    if label.startswith("left_") or label.startswith("right_"):
        item_no = 0 if label.startswith("left_") else 1
        field = "title" if label.endswith("_title") else "body"
        items = slide_spec.get("items", [])
        return items[item_no].get(field, "") if item_no < len(items) else ""

    if label.startswith("col") and ("_title" in label or "_body" in label):
        col_no = int(label[3]) - 1
        field = "title" if label.endswith("_title") else "body"
        items = slide_spec.get("items", [])
        return items[col_no].get(field, "") if col_no < len(items) else ""

    if label.startswith("grid") and ("_title" in label or "_body" in label):
        grid_no = int(label[4]) - 1
        field = "title" if label.endswith("_title") else "body"
        items = slide_spec.get("items", [])
        return items[grid_no].get(field, "") if grid_no < len(items) else ""

    if label.startswith("item") and ("_title" in label or "_body" in label):
        item_no = int(label[4]) - 1
        field = "title" if label.endswith("_title") else "body"
        items = slide_spec.get("items", [])
        return items[item_no].get(field, "") if item_no < len(items) else ""

    if label.startswith("metric"):
        metric_no = int(label[6]) - 1
        metrics = slide_spec.get("keyNumbers", [])
        if metric_no >= len(metrics):
            return ""
        metric = metrics[metric_no]
        if label.endswith("_number"):
            return metric.get("number", "")
        if label.endswith("_label"):
            return metric.get("label", "")
        if label.endswith("_desc"):
            return metric.get("desc", "")

    if "caption" in label.lower() or label.endswith("_desc"):
        images = slide_spec.get("images", [])
        match = re.search(r"(\d+)", label)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(images):
                return str(images[idx].get("caption", ""))
    return ""


def build_placeholder_labels(layout_index: list[dict[str, Any]]) -> dict[int, dict[int, str]]:
    """Build layoutIndex -> placeholder idx -> label from layout_index.json."""

    labels_by_layout: dict[int, dict[int, str]] = {}
    for layout in layout_index:
        labels_by_layout[layout["layoutIndex"]] = {
            ph["idx"]: ph["label"] for ph in layout.get("placeholders", [])
        }
    return labels_by_layout


def enrich_labels_from_template(
    prs: Presentation,
    labels_by_layout: dict[int, dict[int, str]],
) -> dict[int, dict[int, str]]:
    """Merge runtime placeholder names from the pptx template."""

    for layout_index, layout in enumerate(prs.slide_layouts):
        labels_by_layout.setdefault(layout_index, {})
        for placeholder in layout.placeholders:
            labels_by_layout[layout_index].setdefault(
                placeholder.placeholder_format.idx,
                placeholder.name,
            )
    return labels_by_layout


def _caption_placeholders(slide: Slide) -> list[tuple[Any, str]]:
    """Collect non-picture placeholders whose labels suggest captions."""

    result: list[tuple[Any, str]] = []
    for shape in slide.placeholders:
        ph_format = shape.placeholder_format
        if ph_format.type == PP_PLACEHOLDER.PICTURE:
            continue
        label = shape.name
        if "caption" in label.lower() or re.search(r"img\d+_desc|image\d+_desc", label, re.I):
            result.append((shape, label))
    return result


def fill_slide_content(
    slide: Slide,
    slide_spec: dict[str, Any],
    labels: dict[int, str],
    *,
    image_paths: list[Path],
) -> list[str]:
    """Fill text and picture placeholders; return warning messages."""

    warnings: list[str] = []
    picture_slots: list[Any] = []
    for shape in slide.placeholders:
        ph_format = shape.placeholder_format
        if ph_format.type == PP_PLACEHOLDER.PICTURE:
            picture_slots.append(shape)

    for index, image_path in enumerate(image_paths):
        if index >= len(picture_slots):
            warnings.append(f"no picture placeholder for image index {index + 1}")
            break
        placeholder = picture_slots[index]
        try:
            placeholder.insert_picture(str(image_path))
        except Exception as exc:
            raise OSError(f"failed to insert image {image_path}: {exc}") from exc

    for shape in slide.placeholders:
        ph_format = shape.placeholder_format
        if ph_format.type == PP_PLACEHOLDER.PICTURE:
            continue
        label = labels.get(ph_format.idx, shape.name)
        value = value_for_label(slide_spec, label)
        if value:
            if not hasattr(shape, "text_frame"):
                continue
            shape.text = value

    for shape, label in _caption_placeholders(slide):
        value = value_for_label(slide_spec, label)
        if value and hasattr(shape, "text_frame"):
            shape.text = value

    return warnings


def remove_all_existing_slides(prs: Presentation) -> None:
    """Remove all slides from a presentation, keeping slide layouts."""

    slide_id_list = prs.slides._sldIdLst
    for slide_id in list(slide_id_list):
        rel_id = slide_id.rId
        prs.part.drop_rel(rel_id)
        slide_id_list.remove(slide_id)
