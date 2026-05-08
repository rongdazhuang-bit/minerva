"""Tests for PaddleOCR-VL HTTP client (mocked transport, no real serving stack)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.ocr.paddleocr import LayoutParsingRequest
from app.ocr.paddleocr import PaddleOcrVlApiError
from app.ocr.paddleocr import PaddleOcrVlParseError
from app.ocr.paddleocr import PaddleOcrVlTransportError
from app.ocr.paddleocr import PrunedResult
from app.ocr.paddleocr import RestructurePageItem
from app.ocr.paddleocr import RestructurePagesRequest
from app.ocr.paddleocr import layout_parsing_body
from app.ocr.paddleocr import paddleocr_default_timeout
from app.ocr.paddleocr import post_layout_parsing
from app.ocr.paddleocr import post_restructure_pages


def _minimal_pruned_result_dict() -> dict:
    """Smallest ``prunedResult`` that satisfies :class:`PrunedResult` validation."""
    return {
        "page_count": 1,
        "width": 100,
        "height": 100,
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
        "parsing_res_list": [],
        "layout_det_res": {"boxes": []},
    }


def _success_envelope() -> dict:
    """Minimal valid success payload matching PaddleOCR-VL 4.3."""
    return {
        "logId": "test-log",
        "errorCode": 0,
        "errorMsg": "Success",
        "result": {
            "layoutParsingResults": [
                {
                    "prunedResult": _minimal_pruned_result_dict(),
                    "markdown": {"text": "# Hi", "images": {}},
                }
            ],
            "dataInfo": {},
        },
    }


@pytest.mark.asyncio
async def test_post_layout_parsing_serializes_camel_case() -> None:
    """Request JSON uses camelCase aliases; URL path is not rewritten by the client."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_success_envelope())

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as ac:
        req = LayoutParsingRequest(file="YmFzZTY0", file_type=1)
        out = await post_layout_parsing(
            "http://paddle.example.com:8080/layout-parsing",
            req,
            client=ac,
        )

    assert captured["url"] == "http://paddle.example.com:8080/layout-parsing"
    assert captured["body"]["file"] == "YmFzZTY0"
    assert captured["body"]["fileType"] == 1
    assert out.result is not None
    assert len(out.result.layout_parsing_results) == 1
    assert out.result.layout_parsing_results[0].markdown is not None
    assert out.result.layout_parsing_results[0].markdown.text == "# Hi"
    pr = out.result.layout_parsing_results[0].pruned_result
    assert pr is not None
    assert pr.page_count == 1
    assert pr.layout_det_res.boxes == []


@pytest.mark.asyncio
async def test_layout_parsing_api_error_raises() -> None:
    """Non-zero errorCode yields PaddleOcrVlApiError with log metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "logId": "bad",
                "errorCode": 400,
                "errorMsg": "bad request",
                "result": None,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as ac:
        with pytest.raises(PaddleOcrVlApiError) as exc_info:
            await post_layout_parsing(
                "http://x/layout-parsing",
                LayoutParsingRequest(file="x"),
                client=ac,
            )
    err = exc_info.value
    assert err.log_id == "bad"
    assert err.error_code == 400
    assert err.error_msg == "bad request"


@pytest.mark.asyncio
async def test_transport_error_on_http_status() -> None:
    """HTTP failure maps to PaddleOcrVlTransportError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as ac:
        with pytest.raises(PaddleOcrVlTransportError) as exc_info:
            await post_layout_parsing(
                "http://x/layout-parsing",
                LayoutParsingRequest(file="x"),
                client=ac,
            )
    assert exc_info.value.status_code == 503
    assert "upstream" in (exc_info.value.body_snippet or "")


@pytest.mark.asyncio
async def test_parse_error_on_invalid_json() -> None:
    """Invalid JSON maps to PaddleOcrVlParseError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as ac:
        with pytest.raises(PaddleOcrVlParseError):
            await post_layout_parsing(
                "http://x/layout-parsing",
                LayoutParsingRequest(file="x"),
                client=ac,
            )


@pytest.mark.asyncio
async def test_post_restructure_pages_round_trip() -> None:
    """Restructure endpoint uses the same envelope and serializes ``pages``."""

    minimal = PrunedResult.model_validate(_minimal_pruned_result_dict())
    expected_pruned = minimal.model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["concatenatePages"] is True
        assert len(body["pages"]) == 1
        assert body["pages"][0]["prunedResult"] == expected_pruned
        return httpx.Response(200, json=_success_envelope())

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as ac:
        await post_restructure_pages(
            "http://paddle.example.com:8080/restructure-pages",
            RestructurePagesRequest(
                pages=[RestructurePageItem(pruned_result=minimal)],
                concatenate_pages=True,
            ),
            client=ac,
        )


def test_pruned_result_parses_service_like_payload() -> None:
    """Accept a ``prunedResult`` shaped like production PaddleOCR-VL JSON (subset)."""
    raw = {
        "page_count": 5,
        "width": 1191,
        "height": 1684,
        "model_settings": {
            "use_doc_preprocessor": False,
            "use_layout_detection": True,
            "use_chart_recognition": False,
            "use_seal_recognition": True,
            "use_ocr_for_image_block": False,
            "format_block_content": True,
            "merge_layout_blocks": True,
            "markdown_ignore_labels": ["number", "footnote"],
            "return_layout_polygon_points": True,
        },
        "parsing_res_list": [
            {
                "block_label": "text",
                "block_content": "ICS 35.240.15",
                "block_bbox": [136, 56, 276, 80],
                "block_id": 0,
                "block_order": 1,
                "group_id": 0,
                "global_block_id": 0,
                "global_group_id": 0,
                "block_polygon_points": [[136, 56], [276, 56], [276, 80], [136, 80]],
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
                "block_polygon_points": [[804, 69], [1045, 69], [1045, 191], [804, 191]],
            },
        ],
        "layout_det_res": {
            "boxes": [
                {
                    "cls_id": 22,
                    "label": "text",
                    "score": 0.5282134413719177,
                    "coordinate": [136, 56, 276, 80],
                    "order": 1,
                    "polygon_points": [[136, 56], [276, 56], [276, 80], [136, 80]],
                },
                {
                    "cls_id": 13,
                    "label": "header_image",
                    "score": 0.786074161529541,
                    "coordinate": [804, 69, 1045, 191],
                    "order": None,
                    "polygon_points": [[804, 69], [1045, 69], [1045, 191], [804, 191]],
                },
            ]
        },
    }
    pr = PrunedResult.model_validate(raw)
    assert pr.page_count == 5
    assert pr.model_settings.use_seal_recognition is True
    assert pr.parsing_res_list[0].block_content == "ICS 35.240.15"
    assert pr.parsing_res_list[1].block_order is None
    assert pr.layout_det_res.boxes[0].score == pytest.approx(0.5282134413719177)
    assert pr.layout_det_res.boxes[1].order is None


def test_layout_parsing_body_exclude_none() -> None:
    """Optional fields omitted when None and exclude_none is True."""
    body = LayoutParsingRequest(file="Zg==")
    d = layout_parsing_body(body, exclude_none=True)
    assert d == {"file": "Zg=="}
    assert "fileType" not in d


def test_paddleocr_default_timeout_splits_read_and_write() -> None:
    """Defaults use distinct read vs write limits (large uploads vs slow inference)."""
    t = paddleocr_default_timeout()
    assert t.connect == 10.0
    assert t.read == 120.0
    assert t.write == 300.0
    assert t.pool == 5.0


@pytest.mark.asyncio
async def test_post_layout_parsing_custom_httpx_timeout_object() -> None:
    """Callers may pass ``httpx.Timeout`` for fine-grained control."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_envelope())

    transport = httpx.MockTransport(handler)
    custom = httpx.Timeout(connect=1.0, read=2.0, write=3.0, pool=4.0)
    async with httpx.AsyncClient(transport=transport, timeout=custom) as ac:
        await post_layout_parsing(
            "http://x/layout-parsing",
            LayoutParsingRequest(file="x"),
            client=ac,
        )
