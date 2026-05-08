"""Async HTTP client for PaddleOCR-VL service endpoints (full URL from caller)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError

from app.ocr.paddleocr.errors import PaddleOcrVlApiError
from app.ocr.paddleocr.errors import PaddleOcrVlParseError
from app.ocr.paddleocr.errors import PaddleOcrVlTransportError
from app.ocr.paddleocr.schemas import LayoutParsingApiResponse
from app.ocr.paddleocr.schemas import LayoutParsingRequest
from app.ocr.paddleocr.schemas import RestructurePagesRequest

# Cap stored error text to keep logs and exceptions bounded.
_BODY_SNIPPET_LEN = 4096

_JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

# Default per-phase timeouts when the caller does not inject an ``AsyncClient``.
# Write is generous for large Base64 payloads; read for slow VLM inference.
_DEFAULT_CONNECT_S = 10.0
_DEFAULT_READ_S = 120.0
_DEFAULT_WRITE_S = 300.0
_DEFAULT_POOL_S = 5.0


def paddleocr_default_timeout(
    *,
    connect: float = _DEFAULT_CONNECT_S,
    read: float = _DEFAULT_READ_S,
    write: float = _DEFAULT_WRITE_S,
    pool: float = _DEFAULT_POOL_S,
) -> httpx.Timeout:
    """
    Return httpx timeouts suited to PaddleOCR-VL JSON calls (upload + long inference).

    Callers may pass this to ``httpx.AsyncClient(timeout=...)`` or rely on ``post_*``
    defaults when ``client`` is omitted.
    """
    return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)


def _resolve_internal_client_timeout(
    timeout: httpx.Timeout | float | None,
) -> httpx.Timeout:
    """Normalize ``timeout`` for a short-lived ``AsyncClient`` created inside ``post_*``."""
    if timeout is None:
        return paddleocr_default_timeout()
    if isinstance(timeout, httpx.Timeout):
        return timeout
    value = float(timeout)
    return httpx.Timeout(
        connect=_DEFAULT_CONNECT_S,
        read=value,
        write=value,
        pool=_DEFAULT_POOL_S,
    )


def _merge_headers(extra: Mapping[str, str] | None) -> dict[str, str]:
    """Merge default JSON headers with caller overrides (caller wins on key clash)."""
    out = dict(_JSON_HEADERS)
    if extra:
        out.update(extra)
    return out


def _snippet(text: str, max_len: int = _BODY_SNIPPET_LEN) -> str:
    """Return ``text`` or a truncated prefix for exception messages."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def layout_parsing_body(
    body: LayoutParsingRequest,
    *,
    exclude_none: bool = True,
) -> dict[str, Any]:
    """Serialize ``LayoutParsingRequest`` to a JSON-ready dict with camelCase keys."""
    return body.model_dump(mode="json", by_alias=True, exclude_none=exclude_none)


def restructure_pages_body(
    body: RestructurePagesRequest,
    *,
    exclude_none: bool = True,
) -> dict[str, Any]:
    """Serialize ``RestructurePagesRequest`` to a JSON-ready dict with camelCase keys."""
    return body.model_dump(mode="json", by_alias=True, exclude_none=exclude_none)


def _parse_envelope(raw_text: str) -> LayoutParsingApiResponse:
    """Parse and validate the top-level serving JSON envelope."""
    try:
        data: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PaddleOcrVlParseError(
            "PaddleOCR-VL response is not valid JSON",
            raw_body=_snippet(raw_text),
        ) from exc
    if not isinstance(data, dict):
        raise PaddleOcrVlParseError(
            "PaddleOCR-VL response JSON must be an object",
            raw_body=_snippet(raw_text),
        )
    try:
        return LayoutParsingApiResponse.model_validate(data)
    except ValidationError as exc:
        raise PaddleOcrVlParseError(
            f"PaddleOCR-VL response does not match schema: {exc}",
            raw_body=_snippet(raw_text),
        ) from exc


def _ensure_api_success(envelope: LayoutParsingApiResponse, raw_text: str) -> None:
    """Raise if the serving layer reports a non-zero ``errorCode``."""
    if envelope.error_code == 0:
        return
    raise PaddleOcrVlApiError(
        f"PaddleOCR-VL API error: {envelope.error_msg}",
        log_id=envelope.log_id,
        error_code=envelope.error_code,
        error_msg=envelope.error_msg,
        raw_body=_snippet(raw_text),
    )


async def _post_envelope(
    url: str,
    payload: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    headers: Mapping[str, str] | None,
) -> LayoutParsingApiResponse:
    """POST JSON to ``url`` and return a validated envelope."""
    hdrs = _merge_headers(headers)
    try:
        response = await client.post(url, json=payload, headers=hdrs)
    except httpx.RequestError as exc:
        raise PaddleOcrVlTransportError(
            f"PaddleOCR-VL request failed: {exc}",
            url=url,
        ) from exc

    raw_text = response.text
    if not response.is_success:
        raise PaddleOcrVlTransportError(
            f"PaddleOCR-VL HTTP {response.status_code}",
            status_code=response.status_code,
            url=str(response.request.url),
            body_snippet=_snippet(raw_text),
        )

    envelope = _parse_envelope(raw_text)
    _ensure_api_success(envelope, raw_text)
    return envelope


async def post_layout_parsing(
    url: str,
    body: LayoutParsingRequest,
    *,
    client: httpx.AsyncClient | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: httpx.Timeout | float | None = None,
    exclude_none: bool = True,
) -> LayoutParsingApiResponse:
    """
    Call layout-parsing (infer) at the exact ``url`` provided by the caller.

    ``url`` must already include the path (e.g. ``.../layout-parsing``).

    When ``client`` is omitted, ``timeout`` controls a new ``AsyncClient``: ``None``
    uses :func:`paddleocr_default_timeout` (separate connect/read/write/pool); a
    ``float`` sets the same value for **read** and **write** while keeping default
    connect/pool; pass ``httpx.Timeout(...)`` for full control. An injected
    ``client`` ignores ``timeout`` (configure the client instead).
    """
    payload = layout_parsing_body(body, exclude_none=exclude_none)
    if client is None:
        t = _resolve_internal_client_timeout(timeout)
        async with httpx.AsyncClient(timeout=t) as ac:
            return await _post_envelope(url, payload, client=ac, headers=headers)
    return await _post_envelope(url, payload, client=client, headers=headers)


async def post_restructure_pages(
    url: str,
    body: RestructurePagesRequest,
    *,
    client: httpx.AsyncClient | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: httpx.Timeout | float | None = None,
    exclude_none: bool = True,
) -> LayoutParsingApiResponse:
    """
    Call restructure-pages at the exact ``url`` provided by the caller.

    ``url`` must already include the path (e.g. ``.../restructure-pages``).

    Timeout behavior matches :func:`post_layout_parsing`.
    """
    payload = restructure_pages_body(body, exclude_none=exclude_none)
    if client is None:
        t = _resolve_internal_client_timeout(timeout)
        async with httpx.AsyncClient(timeout=t) as ac:
            return await _post_envelope(url, payload, client=ac, headers=headers)
    return await _post_envelope(url, payload, client=client, headers=headers)
