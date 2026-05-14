"""Structured ``prunedResult`` objects returned by PaddleOCR-VL layout-parsing (snake_case JSON keys)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PrunedModelSettings(BaseModel):
    """Pipeline flags and markdown label filters echoed in the pruned result."""

    model_config = ConfigDict(extra="ignore")

    use_doc_preprocessor: bool
    use_layout_detection: bool
    use_chart_recognition: bool
    use_seal_recognition: bool
    use_ocr_for_image_block: bool
    format_block_content: bool
    merge_layout_blocks: bool
    markdown_ignore_labels: list[str] = Field(default_factory=list)
    return_layout_polygon_points: bool


class ParsingResBlock(BaseModel):
    """One block in ``parsing_res_list`` (content, label, geometry, reading order)."""

    model_config = ConfigDict(extra="ignore")

    block_label: str
    block_content: str
    block_bbox: list[float]
    block_id: int
    block_order: int | None = None
    group_id: int
    global_block_id: int
    global_group_id: int
    block_polygon_points: list[list[float]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_missing_global_ids(cls, data: Any) -> Any:
        """
        Some serving builds omit ``global_block_id`` / ``global_group_id``; align with page-local ids.

        Hosted or older stacks may only echo ``block_id`` and ``group_id`` per block.
        """
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "global_block_id" not in out and "block_id" in out:
            out["global_block_id"] = out["block_id"]
        if "global_group_id" not in out and "group_id" in out:
            out["global_group_id"] = out["group_id"]
        return out


class LayoutDetBox(BaseModel):
    """Single layout-detection box under ``layout_det_res.boxes``."""

    model_config = ConfigDict(extra="ignore")

    cls_id: int
    label: str
    score: float
    coordinate: list[float]
    order: int | None = None
    polygon_points: list[list[float]] = Field(default_factory=list)


class LayoutDetRes(BaseModel):
    """Detector boxes aligned with the parsed block list."""

    model_config = ConfigDict(extra="ignore")

    boxes: list[LayoutDetBox] = Field(default_factory=list)


class DocPreprocessorModelSettings(BaseModel):
    """Orientation / unwarp flags nested under ``doc_preprocessor_res.model_settings``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    use_doc_orientation_classify: bool | None = Field(
        default=None, alias="useDocOrientationClassify"
    )
    use_doc_unwarping: bool | None = Field(default=None, alias="useDocUnwarping")


class DocPreprocessorRes(BaseModel):
    """Optional ``doc_preprocessor_res`` on each ``prunedResult`` (angle and preprocessor flags)."""

    model_config = ConfigDict(extra="ignore")

    model_settings: DocPreprocessorModelSettings | None = None
    angle: int | None = None


class PrunedResult(BaseModel):
    """
    PaddleOCR-VL ``prunedResult`` payload (page geometry, settings, blocks, layout boxes).

    Matches the serving JSON shape; extra keys from newer servers are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    page_count: int
    width: int
    height: int
    model_settings: PrunedModelSettings
    parsing_res_list: list[ParsingResBlock] = Field(default_factory=list)
    layout_det_res: LayoutDetRes
    doc_preprocessor_res: DocPreprocessorRes | None = None

    @model_validator(mode="before")
    @classmethod
    def default_layout_det_when_absent(cls, data: Any) -> Any:
        """Hosted responses may omit ``layout_det_res``; normalize to an empty detector list."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if out.get("layout_det_res") is None:
            out["layout_det_res"] = {"boxes": []}
        return out
