"""Unit tests for Paddle prunedResult → LayoutPage conversion."""

from app.layout.from_paddle import layout_page_from_pruned
from app.ocr.paddleocr.pruned_result import PrunedResult


def _minimal_pruned_dict(*, extra_blocks: list[dict] | None = None) -> dict:
    """Build a minimal prunedResult-shaped dict for tests."""
    blocks = [
        {
            "block_label": "text",
            "block_content": "ICS 35.240.15",
            "block_bbox": [136, 56, 276, 80],
            "block_id": 0,
            "block_order": 1,
            "group_id": 0,
            "global_block_id": 0,
            "global_group_id": 0,
        },
        {
            "block_label": "header_image",
            "block_content": "<div></div>\n",
            "block_bbox": [804, 69, 1045, 191],
            "block_id": 2,
            "block_order": None,
            "group_id": 2,
            "global_block_id": 2,
            "global_group_id": 2,
        },
    ]
    if extra_blocks:
        blocks.extend(extra_blocks)
    return {
        "page_count": 1,
        "width": 1191,
        "height": 1684,
        "model_settings": {
            "use_doc_preprocessor": False,
            "use_layout_detection": True,
            "use_chart_recognition": False,
            "use_seal_recognition": False,
            "use_ocr_for_image_block": False,
            "format_block_content": True,
            "merge_layout_blocks": True,
            "markdown_ignore_labels": [],
            "return_layout_polygon_points": False,
        },
        "parsing_res_list": blocks,
        "layout_det_res": {"boxes": []},
    }


def test_layout_page_from_pruned_text_and_figure() -> None:
    """Text blocks are translatable; header_image maps to skip figure."""
    pr = PrunedResult.model_validate(_minimal_pruned_dict())
    page = layout_page_from_pruned(0, pr)
    text_block = next(b for b in page.blocks if b.block_key == "p0.b0")
    figure_block = next(b for b in page.blocks if b.block_key == "p0.b2")
    assert text_block.source_text == "ICS 35.240.15"
    assert text_block.skip_translate is False
    assert figure_block.label == "figure"
    assert figure_block.skip_translate is True


def test_layout_page_formula_block() -> None:
    """Formula blocks keep LaTeX and skip translation."""
    pr = PrunedResult.model_validate(
        _minimal_pruned_dict(
            extra_blocks=[
                {
                    "block_label": "formula",
                    "block_content": "$E=mc^2$",
                    "block_bbox": [10, 10, 100, 30],
                    "block_id": 5,
                    "block_order": 3,
                    "group_id": 5,
                    "global_block_id": 5,
                    "global_group_id": 5,
                }
            ]
        )
    )
    page = layout_page_from_pruned(0, pr)
    formula = next(b for b in page.blocks if b.block_key == "p0.b5")
    assert formula.label == "formula"
    assert formula.skip_translate is True
    assert formula.source_text == "$E=mc^2$"
