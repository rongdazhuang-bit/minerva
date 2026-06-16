"""Build fill plans from outline JSON and slide library."""

from __future__ import annotations

from typing import Any

from app.agent.skills.ppt.pptmaker.normalize import expand_outline_with_meta

_SCHEMA = "template_fill_pptx_plan.v1"
_ROLE_TITLE = "title_candidate"
_ROLE_BODY = "body_candidate"
_ROLE_LABEL = "label_candidate"


def _slides_by_page_type(library: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group library slides by page_type."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for slide in library.get("slides", []):
        if not isinstance(slide, dict):
            continue
        page_type = str(slide.get("page_type", "content_candidate"))
        grouped.setdefault(page_type, []).append(slide)
    return grouped


def _slots_by_role(slide: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group slots on one library slide by role."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for slot in slide.get("slots", []):
        if not isinstance(slot, dict):
            continue
        role = str(slot.get("role", _ROLE_BODY))
        grouped.setdefault(role, []).append(slot)
    return grouped


def _pick_library_slide(
    candidates: list[dict[str, Any]],
    *,
    body_slot_need: int,
) -> dict[str, Any] | None:
    """Pick the best library slide from candidates by body slot count."""

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def score(slide: dict[str, Any]) -> tuple[int, int]:
        roles = _slots_by_role(slide)
        body_count = len(roles.get(_ROLE_BODY, []))
        label_count = len(roles.get(_ROLE_LABEL, []))
        diff = abs(body_count - body_slot_need)
        return (diff, -(body_count + label_count))

    return min(candidates, key=score)


def _body_texts_from_spec(slide_spec: dict[str, Any]) -> list[str]:
    """Collect body replacement strings from a normalized slide spec."""

    texts: list[str] = []
    page_type = slide_spec.get("pageType")
    if page_type == "cover":
        subtitle = str(slide_spec.get("subtitle", "")).strip()
        if subtitle:
            texts.append(subtitle)
        return texts

    items = slide_spec.get("items") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        body = str(item.get("body", "")).strip()
        if title and body:
            texts.append(f"{title}：{body}")
        elif title:
            texts.append(title)
        elif body:
            texts.append(body)

    body = str(slide_spec.get("body", "")).strip()
    if body:
        texts.append(body)

    for metric in slide_spec.get("keyNumbers") or []:
        if not isinstance(metric, dict):
            continue
        number = str(metric.get("number", "")).strip()
        label = str(metric.get("label", "")).strip()
        desc = str(metric.get("desc", "")).strip()
        line = " ".join(part for part in (number, label, desc) if part)
        if line:
            texts.append(line)

    return texts


def _build_replacements(
    library_slide: dict[str, Any],
    slide_spec: dict[str, Any],
) -> list[dict[str, str]]:
    """Map outline fields to slot replacements on a library slide."""

    roles = _slots_by_role(library_slide)
    replacements: list[dict[str, str]] = []
    page_type = slide_spec.get("pageType")

    title_slots = roles.get(_ROLE_TITLE, [])
    body_slots = roles.get(_ROLE_BODY, [])
    label_slots = roles.get(_ROLE_LABEL, [])

    page_title = str(slide_spec.get("pageTitle", "")).strip()
    if page_title and title_slots:
        replacements.append({"slot_id": str(title_slots[0]["slot_id"]), "text": page_title})
    elif page_title and body_slots and page_type == "cover":
        replacements.append({"slot_id": str(body_slots[0]["slot_id"]), "text": page_title})

    body_texts = _body_texts_from_spec(slide_spec)
    if page_type == "cover":
        subtitle = str(slide_spec.get("subtitle", "")).strip()
        if subtitle:
            target_slots = title_slots[1:] if len(title_slots) > 1 else body_slots or label_slots
            if target_slots:
                replacements.append({"slot_id": str(target_slots[0]["slot_id"]), "text": subtitle})
        return replacements

    remaining_bodies = list(body_slots)
    if not remaining_bodies:
        remaining_bodies = list(label_slots)
    for idx, text in enumerate(body_texts):
        if idx >= len(remaining_bodies):
            break
        replacements.append({"slot_id": str(remaining_bodies[idx]["slot_id"]), "text": text})

    return replacements


def outline_to_fill_plan(
    outline: dict[str, Any],
    library: dict[str, Any],
    *,
    source_pptx: str = "",
) -> dict[str, Any]:
    """Build ``template_fill_pptx_plan.v1`` from outline and library using layout-first rules."""

    slide_specs = expand_outline_with_meta(outline)
    grouped = _slides_by_page_type(library)
    cover_pool = grouped.get("cover_candidate", [])
    content_pool = grouped.get("content_candidate", []) or grouped.get("section_candidate", [])
    if not content_pool:
        content_pool = [s for s in library.get("slides", []) if isinstance(s, dict)]

    plan_slides: list[dict[str, Any]] = []
    for slide_spec in slide_specs:
        page_type = slide_spec.get("pageType")
        if page_type == "cover":
            library_slide = _pick_library_slide(cover_pool, body_slot_need=0) or cover_pool[0] if cover_pool else None
        else:
            body_need = len(_body_texts_from_spec(slide_spec))
            library_slide = _pick_library_slide(content_pool, body_slot_need=max(body_need, 1))
        if library_slide is None:
            continue
        replacements = _build_replacements(library_slide, slide_spec)
        notes = str(slide_spec.get("speakerNotes", "")).strip()
        entry: dict[str, Any] = {
            "source_slide": int(library_slide["slide_index"]),
            "replacements": replacements,
        }
        if notes:
            entry["notes"] = notes
        plan_slides.append(entry)

    return {
        "schema": _SCHEMA,
        "source_pptx": source_pptx or str(library.get("source_pptx", "")),
        "slides": plan_slides,
    }
