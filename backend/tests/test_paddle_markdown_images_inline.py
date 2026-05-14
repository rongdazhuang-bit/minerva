"""Tests for :mod:`app.file_ocr.service.paddle_markdown_images`."""

from __future__ import annotations

import httpx
import pytest

from app.file_ocr.service.paddle_markdown_images import inline_http_markdown_images_to_data_uris


@pytest.mark.asyncio
async def test_inline_rewrites_https_to_data_uri() -> None:
    """HTTP(S) image bodies are turned into ``data:image/...;base64,...``."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.com"
        return httpx.Response(
            200,
            content=b"\xff\xd8\xff\xd9",
            headers={"content-type": "image/jpeg"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        out = await inline_http_markdown_images_to_data_uris(
            {"imgs/a.jpg": "https://example.com/x.jpg"},
            client=client,
        )
    assert out["imgs/a.jpg"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_inline_preserves_data_uri_and_relative_paths() -> None:
    """Existing ``data:`` values and non-URL strings are not fetched."""

    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not GET")

    transport = httpx.MockTransport(boom)
    async with httpx.AsyncClient(transport=transport) as client:
        out = await inline_http_markdown_images_to_data_uris(
            {
                "x": "data:image/png;base64,QQ==",
                "y": "/relative/path.png",
            },
            client=client,
        )
    assert out["x"] == "data:image/png;base64,QQ=="
    assert out["y"] == "/relative/path.png"


@pytest.mark.asyncio
async def test_inline_http_error_keeps_original_url() -> None:
    """When GET fails, the map entry stays as the original URL string."""

    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    url = "https://example.com/missing.jpg"
    async with httpx.AsyncClient(transport=transport) as client:
        out = await inline_http_markdown_images_to_data_uris({"k": url}, client=client)
    assert out["k"] == url
