"""Orchestrate svg_design engine: validate specs and export SVG pages to pptx."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.skills.ppt.pptmaker.generate import PptGenerateError
from app.agent.skills.ppt.svg_pipeline.export import SvgExportError, export_svgs_to_pptx
from app.agent.skills.ppt.svg_pipeline.finalize import finalize_svg_pages


def generate_svg_presentation(
    *,
    workspace_id: uuid.UUID,
    output_path: str,
    svg_dir: Path,
    design_spec_path: Path,
    spec_lock_path: Path,
    transition: str = "fade",
) -> dict[str, Any]:
    """Finalize SVG pages and export an editable pptx into the workspace sandbox."""

    if not design_spec_path.is_file():
        raise PptGenerateError(
            "design_spec_missing",
            f"design spec not found: {design_spec_path}",
        )
    if not spec_lock_path.is_file():
        raise PptGenerateError(
            "design_spec_missing",
            f"spec lock not found: {spec_lock_path}",
        )

    assets_dir = svg_dir / "assets"
    svg_paths = finalize_svg_pages(svg_dir, assets_dir=assets_dir)
    if not svg_paths:
        raise PptGenerateError(
            "svg_export_failed",
            f"no page_*.svg files in {svg_dir}",
        )

    sandbox = AgentFileSandbox(workspace_id=workspace_id)
    out_rel = output_path.strip() or "output/presentation.pptx"
    try:
        dest = sandbox.resolve(out_rel)
    except AgentFileSandbox.Error as exc:
        raise PptGenerateError("write_failed", exc.message) from exc

    try:
        slide_count = export_svgs_to_pptx(
            svg_paths,
            dest,
            transition=transition if transition else "fade",
        )
    except SvgExportError as exc:
        code = exc.code if exc.code in {"design_spec_missing", "svg_export_failed"} else "svg_export_failed"
        raise PptGenerateError(code, exc.message) from exc

    pages = [
        {"page": index, "svg": svg_path.name}
        for index, svg_path in enumerate(svg_paths, start=1)
    ]

    return {
        "ok": True,
        "engine": "svg_design",
        "output_path": out_rel.replace("\\", "/"),
        "pages": pages,
        "warnings": [] if slide_count == len(svg_paths) else ["slide count mismatch"],
    }
