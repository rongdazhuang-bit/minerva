"""Orchestrate PPT generation from outline to output file."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from pptx import Presentation

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.skills.ppt.pptmaker.constants import DEFAULT_LAYOUT_INDEX_PATH, DEFAULT_TEMPLATE_PATH
from app.agent.skills.ppt.pptmaker.fill import (
    build_placeholder_labels,
    enrich_labels_from_template,
    fill_slide_content,
    remove_all_existing_slides,
)
from app.agent.skills.ppt.pptmaker.layout_select import select_layout_name
from app.agent.skills.ppt.pptmaker.normalize import expand_outline_with_meta

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


class PptGenerateError(Exception):
    """Structured generation failure."""

    def __init__(self, code: str, message: str) -> None:
        """Store error code and message."""

        super().__init__(message)
        self.code = code
        self.message = message


def _load_layout_index(path: Path) -> list[dict[str, Any]]:
    """Load layout index JSON from disk."""

    if not path.is_file():
        raise PptGenerateError("template_missing", f"layout index not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_image_paths(
    sandbox: AgentFileSandbox,
    slide_spec: dict[str, Any],
) -> list[Path]:
    """Resolve sandbox-relative image paths to absolute paths."""

    paths: list[Path] = []
    for image in slide_spec.get("images", []):
        if not isinstance(image, dict):
            continue
        rel = str(image.get("path", "")).strip()
        if not rel:
            continue
        try:
            resolved = sandbox.resolve(rel)
        except AgentFileSandbox.Error as exc:
            raise PptGenerateError("image_load_failed", exc.message) from exc
        if not resolved.is_file():
            raise PptGenerateError("image_load_failed", f"image not found: {rel}")
        if resolved.suffix.lower() not in _IMAGE_SUFFIXES:
            raise PptGenerateError("image_load_failed", f"unsupported image type: {rel}")
        paths.append(resolved)
    return paths


async def generate_presentation(
    outline: dict[str, Any],
    *,
    workspace_id: uuid.UUID,
    output_path: str,
    layout_mode: str = "hybrid",
    chat_model: BaseChatModel | None = None,
    template_path: Path | None = None,
    layout_index_path: Path | None = None,
) -> dict[str, Any]:
    """Generate a pptx file in the workspace sandbox from an outline dict."""

    template = template_path or DEFAULT_TEMPLATE_PATH
    layout_json = layout_index_path or DEFAULT_LAYOUT_INDEX_PATH
    if not template.is_file():
        raise PptGenerateError("template_missing", f"template not found: {template}")

    slide_specs = expand_outline_with_meta(outline)
    layout_index = _load_layout_index(layout_json)
    sandbox = AgentFileSandbox(workspace_id=workspace_id)

    prs = Presentation(str(template))
    labels_by_layout = enrich_labels_from_template(
        prs,
        build_placeholder_labels(layout_index),
    )
    remove_all_existing_slides(prs)

    layout_name_to_index = {layout.name: i for i, layout in enumerate(prs.slide_layouts)}
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []

    for slide_spec in slide_specs:
        layout_name, selection_method, selection_reason = await select_layout_name(
            slide_spec,
            layout_index,
            layout_mode=layout_mode,
            chat_model=chat_model,
        )
        if layout_name not in layout_name_to_index:
            raise PptGenerateError(
                "layout_not_found",
                f"layout not in template: {layout_name}",
            )
        layout_index_no = layout_name_to_index[layout_name]
        slide = prs.slides.add_slide(prs.slide_layouts[layout_index_no])
        labels = labels_by_layout.get(layout_index_no, {})

        image_paths = _resolve_image_paths(sandbox, slide_spec)
        page_warnings = fill_slide_content(
            slide,
            slide_spec,
            labels,
            image_paths=image_paths,
        )
        warnings.extend(page_warnings)

        pages.append(
            {
                "pageTitle": slide_spec.get("pageTitle"),
                "selectedLayout": layout_name,
                "layoutIndex": layout_index_no,
                "selectionMethod": selection_method,
                "reason": selection_reason,
            }
        )

    out_rel = output_path.strip() or "output/presentation.pptx"
    try:
        dest = sandbox.resolve(out_rel)
    except AgentFileSandbox.Error as exc:
        raise PptGenerateError("write_failed", exc.message) from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        prs.save(str(dest))
    except OSError as exc:
        raise PptGenerateError("write_failed", str(exc)) from exc

    return {
        "ok": True,
        "output_path": out_rel.replace("\\", "/"),
        "pages": pages,
        "warnings": warnings,
    }
