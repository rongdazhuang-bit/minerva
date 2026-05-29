"""Tests for MinerU HTTP client."""

from __future__ import annotations

from typing import Any

import pytest

from app.ocr.mineru.client import post_file_parse
from app.ocr.mineru.errors import MineruTransportError


@pytest.mark.asyncio
async def test_post_file_parse_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful multipart POST returns body bytes and content-type."""
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/zip"}
        content = b"PK\x03\x04"
        text = ""

        @property
        def request(self) -> object:
            class R:
                url = "http://127.0.0.1:8000/file_parse"

            return R()

        @property
        def is_success(self) -> bool:
            return True

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            content: object = None,
            headers: object = None,
            **kwargs: object,
        ) -> FakeResponse:
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("app.ocr.mineru.client.httpx.AsyncClient", lambda **kw: FakeClient())
    body, ctype = await post_file_parse(
        "http://127.0.0.1:8000/file_parse",
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        form_data={"output_dir": "./output", "lang_list": ["ch"]},
    )
    assert body.startswith(b"PK")
    assert ctype == "application/zip"
    assert isinstance(captured["content"], bytes)
    assert captured["content"].startswith(b"--")
    hdrs = captured["headers"]
    assert isinstance(hdrs, dict)
    assert str(hdrs.get("Content-Type", "")).startswith("multipart/form-data")


@pytest.mark.asyncio
async def test_post_file_parse_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-success HTTP status raises MineruTransportError."""

    class FakeResponse:
        status_code = 500
        headers: dict[str, str] = {}
        content = b"err"
        text = "err"

        @property
        def request(self) -> object:
            class R:
                url = "http://127.0.0.1:8000/file_parse"

            return R()

        @property
        def is_success(self) -> bool:
            return False

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.ocr.mineru.client.httpx.AsyncClient", lambda **kw: FakeClient())
    with pytest.raises(MineruTransportError):
        await post_file_parse(
            "http://127.0.0.1:8000/file_parse",
            file_name="demo.pdf",
            file_bytes=b"%PDF",
            form_data={"output_dir": "./output"},
        )
