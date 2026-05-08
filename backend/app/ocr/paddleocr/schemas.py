"""Pydantic models for PaddleOCR-VL serving APIs (layout-parsing and restructure-pages)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ocr.paddleocr.pruned_result import PrunedResult

# Flexible JSON fragments allowed by upstream for layout-related knobs.
LayoutThreshold = float | int | dict[str, Any] | list[Any]
LayoutUnclipRatio = float | int | dict[str, Any] | list[Any]
LayoutMergeBboxesMode = str | dict[str, Any] | list[Any]


class LayoutParsingRequest(BaseModel):
    """Request body for ``POST .../layout-parsing`` (infer) per PaddleOCR-VL 4.3."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    file: str = Field(..., min_length=1, description="File URL or Base64 payload.")
    file_type: int | None = Field(default=None, alias="fileType")
    use_doc_orientation_classify: bool | None = Field(
        default=None, alias="useDocOrientationClassify"
    )
    use_doc_unwarping: bool | None = Field(default=None, alias="useDocUnwarping")
    use_layout_detection: bool | None = Field(default=None, alias="useLayoutDetection")
    use_chart_recognition: bool | None = Field(default=None, alias="useChartRecognition")
    use_seal_recognition: bool | None = Field(default=None, alias="useSealRecognition")
    use_ocr_for_image_block: bool | None = Field(default=None, alias="useOcrForImageBlock")
    layout_threshold: LayoutThreshold | None = Field(default=None, alias="layoutThreshold")
    layout_nms: bool | None = Field(default=None, alias="layoutNms")
    layout_unclip_ratio: LayoutUnclipRatio | None = Field(
        default=None, alias="layoutUnclipRatio"
    )
    layout_merge_bboxes_mode: LayoutMergeBboxesMode | None = Field(
        default=None, alias="layoutMergeBboxesMode"
    )
    layout_shape_mode: str | None = Field(default=None, alias="layoutShapeMode")
    prompt_label: str | None = Field(default=None, alias="promptLabel")
    format_block_content: bool | None = Field(default=None, alias="formatBlockContent")
    repetition_penalty: float | int | None = Field(default=None, alias="repetitionPenalty")
    temperature: float | int | None = None
    top_p: float | int | None = Field(default=None, alias="topP")
    min_pixels: float | int | None = Field(default=None, alias="minPixels")
    max_pixels: float | int | None = Field(default=None, alias="maxPixels")
    max_new_tokens: float | int | None = Field(default=None, alias="maxNewTokens")
    merge_layout_blocks: bool | None = Field(default=None, alias="mergeLayoutBlocks")
    markdown_ignore_labels: list[Any] | None = Field(
        default=None, alias="markdownIgnoreLabels"
    )
    vlm_extra_args: dict[str, Any] | None = Field(default=None, alias="vlmExtraArgs")
    prettify_markdown: bool | None = Field(default=None, alias="prettifyMarkdown")
    show_formula_number: bool | None = Field(default=None, alias="showFormulaNumber")
    restructure_pages: bool | None = Field(default=None, alias="restructurePages")
    merge_tables: bool | None = Field(default=None, alias="mergeTables")
    relevel_titles: bool | None = Field(default=None, alias="relevelTitles")
    output_formats: list[Any] | None = Field(default=None, alias="outputFormats")
    visualize: bool | None = None


class MarkdownResult(BaseModel):
    """``markdown`` object on each ``layoutParsingResults`` entry."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    text: str = ""
    images: dict[str, str] = Field(default_factory=dict)


class LayoutParsingPageResult(BaseModel):
    """Single element of ``layoutParsingResults``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    pruned_result: PrunedResult | None = Field(default=None, alias="prunedResult")
    markdown: MarkdownResult | None = None
    output_images: dict[str, str] | None = Field(default=None, alias="outputImages")
    input_image: str | None = Field(default=None, alias="inputImage")
    exports: dict[str, Any] | None = None


class LayoutParsingResultPayload(BaseModel):
    """``result`` object for successful layout-parsing or restructure-pages calls."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    layout_parsing_results: list[LayoutParsingPageResult] = Field(
        default_factory=list, alias="layoutParsingResults"
    )
    data_info: dict[str, Any] | None = Field(default=None, alias="dataInfo")


class LayoutParsingApiResponse(BaseModel):
    """Top-level JSON envelope returned by PaddleOCR-VL serving."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    log_id: str = Field(alias="logId")
    error_code: int = Field(alias="errorCode")
    error_msg: str = Field(alias="errorMsg")
    result: LayoutParsingResultPayload | None = None


class RestructurePageItem(BaseModel):
    """One element of ``pages`` for ``POST .../restructure-pages``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    pruned_result: PrunedResult = Field(alias="prunedResult")
    markdown_images: dict[str, str] | None = Field(default=None, alias="markdownImages")


class RestructurePagesRequest(BaseModel):
    """Request body for ``POST .../restructure-pages``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    pages: list[RestructurePageItem]
    merge_tables: bool | None = Field(default=None, alias="mergeTables")
    relevel_titles: bool | None = Field(default=None, alias="relevelTitles")
    concatenate_pages: bool | None = Field(default=None, alias="concatenatePages")
    prettify_markdown: bool | None = Field(default=None, alias="prettifyMarkdown")
    show_formula_number: bool | None = Field(default=None, alias="showFormulaNumber")
    output_formats: list[Any] | None = Field(default=None, alias="outputFormats")
