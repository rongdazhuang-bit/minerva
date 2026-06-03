"""Async HTTP client for MinerU FastAPI ``POST /file_parse`` (full URL from caller)."""

from __future__ import annotations

from app.core.log import get_logger
import mimetypes
from collections.abc import Mapping

import httpx

from app.ocr.mineru.errors import MineruTransportError

_BODY_SNIPPET_LEN = 4096

_DEFAULT_CONNECT_S = 10.0
_DEFAULT_READ_S = 300.0
_DEFAULT_WRITE_S = 300.0
_DEFAULT_POOL_S = 5.0

log = get_logger(__name__)


def mineru_default_timeout(
    *,
    connect: float = _DEFAULT_CONNECT_S,
    read: float = _DEFAULT_READ_S,
    write: float = _DEFAULT_WRITE_S,
    pool: float = _DEFAULT_POOL_S,
) -> httpx.Timeout:
    """Return httpx timeouts suited to MinerU multipart upload and long parsing."""
    return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)


def _resolve_internal_client_timeout(
    timeout: httpx.Timeout | float | None,
) -> httpx.Timeout:
    """Normalize ``timeout`` for a short-lived ``AsyncClient`` created inside ``post_file_parse``."""
    if timeout is None:
        return mineru_default_timeout()
    if isinstance(timeout, httpx.Timeout):
        return timeout
    value = float(timeout)
    return httpx.Timeout(
        connect=_DEFAULT_CONNECT_S,
        read=value,
        write=value,
        pool=_DEFAULT_POOL_S,
    )


def _snippet(text: str, max_len: int = _BODY_SNIPPET_LEN) -> str:
    """Return ``text`` or a truncated prefix for exception messages."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _multipart_file_parts(
    form_data: dict[str, str | list[str]],
    *,
    file_name: str,
    file_bytes: bytes,
    mime: str,
) -> list[tuple[str, str | tuple[str, bytes, str]]]:
    """Build multipart ``files`` entries (form fields + uploaded document)."""
    parts: list[tuple[str, str | tuple[str, bytes, str]]] = []
    for key, raw in form_data.items():
        if isinstance(raw, list):
            for item in raw:
                parts.append((key, str(item)))
        else:
            parts.append((key, str(raw)))
    parts.append(("files", (file_name, file_bytes, mime)))
    return parts


def _encode_multipart_body(
    form_data: dict[str, str | list[str]],
    *,
    file_name: str,
    file_bytes: bytes,
    mime: str,
) -> tuple[bytes, str]:
    """
    Materialize multipart form bytes in memory for AsyncClient ``content=`` uploads.

    Avoids httpx streaming encoders that may surface as sync-only request bodies.
    """
    parts = _multipart_file_parts(
        form_data,
        file_name=file_name,
        file_bytes=file_bytes,
        mime=mime,
    )
    probe = httpx.Request("POST", "https://example.invalid/file_parse", files=parts)
    stream = probe.stream
    if stream is None:
        raise MineruTransportError("failed to encode MinerU multipart body", url="")
    body = b"".join(stream)
    content_type = probe.headers.get("Content-Type", "multipart/form-data")
    return body, content_type


def _guess_mime(file_name: str) -> str:
    """Guess MIME type for the uploaded source file."""
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"


async def post_file_parse(
    url: str,
    *,
    file_name: str,
    file_bytes: bytes,
    form_data: dict[str, str | list[str]],
    headers: Mapping[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: httpx.Timeout | float | None = None,
) -> tuple[bytes, str]:
    """
    POST multipart to MinerU ``/file_parse`` and return ``(body_bytes, content_type)``.

    ``url`` must already include the path (e.g. ``http://host:8000/file_parse``).
    """
    mime = _guess_mime(file_name)
    body, multipart_content_type = _encode_multipart_body(
        form_data,
        file_name=file_name,
        file_bytes=file_bytes,
        mime=mime,
    )
    hdrs = dict(headers) if headers else {}
    hdrs["Content-Type"] = multipart_content_type
    log.info(
        "MinerU file_parse request url={} file_name={} file_len={} form_keys={} body_len={}",
        url,
        file_name,
        len(file_bytes),
        sorted(form_data.keys()),
        len(body),
    )

    async def _do_post(ac: httpx.AsyncClient) -> tuple[bytes, str]:
        """Execute one POST and map transport failures."""
        try:
            response = await ac.post(url, content=body, headers=hdrs)
        except httpx.RequestError as exc:
            raise MineruTransportError(
                f"MinerU request failed: {exc}",
                url=url,
            ) from exc
        raw_text = response.text
        log.info(
            "MinerU file_parse response url={} http_status={} content_type={} body_len={}",
            str(response.request.url),
            response.status_code,
            response.headers.get("content-type", ""),
            len(response.content),
        )
        if not response.is_success:
            raise MineruTransportError(
                f"MinerU HTTP {response.status_code}",
                status_code=response.status_code,
                url=str(response.request.url),
                body_snippet=_snippet(raw_text),
            )
        content_type = response.headers.get("content-type", "application/octet-stream")
        return response.content, content_type

    if client is None:
        t = _resolve_internal_client_timeout(timeout)
        async with httpx.AsyncClient(timeout=t, follow_redirects=True) as ac:
            return await _do_post(ac)
    return await _do_post(client)
