"""Structured ``prunedResult`` objects returned by PaddleOCR-VL layout-parsing (snake_case JSON keys)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
