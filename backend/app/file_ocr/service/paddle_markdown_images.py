"""Inline remote ``markdown.images`` URLs into ``data:`` URIs for PaddleOCR-VL persistence."""

from __future__ import annotations

from app.core.log import get_logger
import asyncio
import base64
import mimetypes
from urllib.parse import urlparse

import httpx

log = get_logger(__name__)

# Single-image cap to avoid loading multi‑MB raster into DB memory by mistake.
_DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _normalize_image_mime(content_type: str | None, url: str) -> str:
    """Pick a MIME type for a ``data:`` URI from response headers or the URL path."""

    if content_type:
        part = content_type.split(";", maxsplit=1)[0].strip().lower()
        if part and part != "application/octet-stream":
            return part
    guessed, _ = mimetypes.guess_type(url)
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"


def _is_inlineable_http_url(value: str) -> bool:
    """Return true when ``value`` is an absolute ``http``/``https`` URL (not already ``data:``)."""

    s = value.strip()
    if not s or s.lower().startswith("data:"):
        return False
    try:
        parsed = urlparse(s)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


async def inline_http_markdown_images_to_data_uris(
    images: dict[str, str],
    *,
    max_bytes_per_image: int = _DEFAULT_MAX_IMAGE_BYTES,
    timeout: httpx.Timeout | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, str]:
    """
    Replace ``http``/``https`` map values with ``data:<mime>;base64,...`` while keeping other values.

    On download or size errors the original string is kept and a warning is logged.
    When ``client`` is omitted, a short-lived :class:`httpx.AsyncClient` is used.
    """

    if not images:
        return {}
    out: dict[str, str] = dict(images)
    pairs: list[tuple[str, str]] = [
        (k, v.strip()) for k, v in images.items() if isinstance(v, str) and _is_inlineable_http_url(v)
    ]
    if not pairs:
        return out

    owns_client = client is None
    tout = timeout or httpx.Timeout(60.0, connect=10.0)
    if owns_client:
        client = httpx.AsyncClient(timeout=tout, follow_redirects=True)

    async def fetch_one(key: str, url: str) -> tuple[str, str]:
        """GET one image URL and return ``(placeholder_key, data_uri)``."""

        assert client is not None
        resp = await client.get(url)
        resp.raise_for_status()
        body = resp.content
        if len(body) > max_bytes_per_image:
            raise ValueError(
                f"image exceeds max_bytes_per_image ({len(body)} > {max_bytes_per_image})"
            )
        mime = _normalize_image_mime(resp.headers.get("content-type"), url)
        b64 = base64.standard_b64encode(body).decode("ascii")
        return key, f"data:{mime};base64,{b64}"

    try:
        assert client is not None
        results: list[tuple[str, str] | BaseException] = await asyncio.gather(
            *[fetch_one(k, u) for k, u in pairs],
            return_exceptions=True,
        )
    finally:
        if owns_client and client is not None:
            await client.aclose()

    for item in results:
        if isinstance(item, BaseException):
            log.warning("paddle markdown_images inline fetch failed: {}", item)
            continue
        key, data_uri = item
        out[key] = data_uri

    return out
