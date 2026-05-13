"""Unit tests for merging ``sys_ocr_tool.ocr_config`` into Paddle layout-parsing requests."""

from __future__ import annotations

import json
import uuid

import pytest

from app.file_ocr.service.paddle_ocr_request import (
    build_layout_parsing_request_for_tool,
    merge_paddle_layout_parsing_payload,
)
from app.sys.tool.ocr.domain.db.models import SysOcrTool


def _tool(**kwargs: object) -> SysOcrTool:
    """Build a minimal ``SysOcrTool`` row for pure merge tests."""

    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "name": "t",
        "url": "http://127.0.0.1/layout-parsing",
    }
    base.update(kwargs)
    return SysOcrTool(**base)


def test_merge_passes_json_string_ocr_config_fields() -> None:
    """JSON-string ``ocr_config`` should surface vendor flags on the validated model."""

    cfg = {"useDocOrientationClassify": True, "prettifyMarkdown": False}
    tool = _tool(ocr_config=json.dumps(cfg))
    body = build_layout_parsing_request_for_tool(
        file_b64="QUJD",
        file_name="a.pdf",
        object_key="k.pdf",
        tool=tool,
    )
    assert body.file == "QUJD"
    assert body.use_doc_orientation_classify is True
    assert body.prettify_markdown is False


def test_merge_respects_explicit_file_type_from_config() -> None:
    """When ``fileType`` is stored, do not override it with filename-based inference."""

    tool = _tool(ocr_config=json.dumps({"fileType": 0}))
    payload = merge_paddle_layout_parsing_payload(
        file_b64="QQ==",
        file_name="misleading.png",
        object_key="misleading.png",
        tool=tool,
    )
    assert payload["fileType"] == 0


def test_merge_infers_file_type_when_absent() -> None:
    """Without ``fileType`` in config, infer from object key extension."""

    tool = _tool(ocr_config="{}")
    payload = merge_paddle_layout_parsing_payload(
        file_b64="QQ==",
        file_name=None,
        object_key="folder/doc.pdf",
        tool=tool,
    )
    assert payload["fileType"] == 0


def test_merge_strips_stale_file_from_config() -> None:
    """A persisted ``file`` placeholder must never override the runtime Base64 payload."""

    tool = _tool(ocr_config=json.dumps({"file": "should-be-ignored", "temperature": 0.5}))
    body = build_layout_parsing_request_for_tool(
        file_b64="REAL",
        file_name="a.pdf",
        object_key="a.pdf",
        tool=tool,
    )
    assert body.file == "REAL"
    assert body.temperature == 0.5


def test_invalid_ocr_config_json_raises() -> None:
    """Malformed JSON in ``ocr_config`` should fail fast with a clear error."""

    tool = _tool(ocr_config="{not-json")
    with pytest.raises(ValueError, match="not valid JSON"):
        build_layout_parsing_request_for_tool(
            file_b64="QQ==",
            file_name="a.pdf",
            object_key="a.pdf",
            tool=tool,
        )


def test_non_object_ocr_config_json_raises() -> None:
    """Non-empty JSON array must be rejected so we never send an invalid envelope shape."""

    tool = _tool(ocr_config=json.dumps([1, 2, 3]))
    with pytest.raises(ValueError, match="array must be empty"):
        build_layout_parsing_request_for_tool(
            file_b64="QQ==",
            file_name="a.pdf",
            object_key="a.pdf",
            tool=tool,
        )


def test_empty_json_array_ocr_config_is_treated_as_no_options() -> None:
    """Some clients persist ``[]``; treat it like an empty object for compatibility."""

    tool = _tool(ocr_config=json.dumps([]))
    body = build_layout_parsing_request_for_tool(
        file_b64="QQ==",
        file_name="a.pdf",
        object_key="a.pdf",
        tool=tool,
    )
    assert body.file == "QQ=="
