"""Validate a fill plan against a slide library."""

from __future__ import annotations

from typing import Any

from app.agent.skills.ppt.shared.capacity import check_text_overflow
from app.agent.skills.ppt.template_fill.analyze import parse_shape_id_from_slot_id

_PX_TO_PT = 0.75


def _slot_lookup(library: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build slot_id -> slot dict from library slides."""

    lookup: dict[str, dict[str, Any]] = {}
    for slide in library.get("slides", []):
        if not isinstance(slide, dict):
            continue
        for slot in slide.get("slots", []):
            if isinstance(slot, dict) and slot.get("slot_id"):
                lookup[str(slot["slot_id"])] = slot
    return lookup


def check_fill_plan(library: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Return capacity and consistency check results for a fill plan."""

    warnings: list[str] = []
    slots_by_id = _slot_lookup(library)
    plan_slides = plan.get("slides", [])
    if not isinstance(plan_slides, list) or not plan_slides:
        warnings.append("fill plan has no slides")
        return {"passed": False, "warnings": warnings}

    source_count = int(library.get("slide_count", len(library.get("slides", []))))
    for entry in plan_slides:
        if not isinstance(entry, dict):
            warnings.append("invalid slide entry in fill plan")
            continue
        source_slide = entry.get("source_slide")
        if not isinstance(source_slide, int) or source_slide < 1 or source_slide > source_count:
            warnings.append(f"invalid source_slide: {source_slide!r}")
            continue
        for replacement in entry.get("replacements", []):
            if not isinstance(replacement, dict):
                continue
            slot_id = str(replacement.get("slot_id", ""))
            text = str(replacement.get("text", ""))
            if not slot_id:
                warnings.append("replacement missing slot_id")
                continue
            slot = slots_by_id.get(slot_id)
            if slot is None:
                warnings.append(f"unknown slot_id in plan: {slot_id}")
                continue
            geometry = slot.get("geometry") or {}
            metrics = slot.get("text_metrics") or {}
            width_px = float(geometry.get("w", 0))
            font_px = float(metrics.get("font_size_px", 18))
            lines = int(metrics.get("paragraph_count", 1) or 1)
            width_pt = width_px * _PX_TO_PT
            font_pt = font_px * _PX_TO_PT
            label = slot_id
            if parse_shape_id_from_slot_id(slot_id) is not None:
                label = f"{slot.get('role', 'slot')} ({slot_id})"
            warnings.extend(
                check_text_overflow(
                    text=text,
                    width_pt=width_pt,
                    font_size_pt=font_pt,
                    label=label,
                    lines=lines,
                )
            )

    return {"passed": not any("invalid" in w or "unknown" in w or "missing" in w for w in warnings), "warnings": warnings}
