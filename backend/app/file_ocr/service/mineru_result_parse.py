"""Parse MinerU ``/file_parse`` ZIP/JSON responses into per-page OCR results."""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.ocr.mineru.errors import MineruParseError

_BODY_SNIPPET_LEN = 4096


@dataclass(frozen=True)
class MineruPageResult:
    """One page of MinerU output ready for ``ocr_file_mineru`` persistence."""

    page_index: int
    markdown_text: str | None
    markdown_images: dict[str, str] | None
    page_width: int | None
    page_height: int | None


def parse_mineru_response(*, body: bytes, content_type: str) -> list[MineruPageResult]:
    """Dispatch ZIP vs JSON parsing based on ``Content-Type`` and payload magic."""
    ctype = (content_type or "").lower()
    if "zip" in ctype or body[:2] == b"PK":
        return parse_mineru_zip_bytes(body)
    if "json" in ctype:
        return _parse_mineru_json_bytes(body)
    raise MineruParseError(
        f"unsupported MinerU response content-type: {content_type or 'unknown'}",
        raw_body=_snippet(body),
    )


def parse_mineru_zip_bytes(data: bytes) -> list[MineruPageResult]:
    """Safe-extract an in-memory ZIP and build per-page markdown rows."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as exc:
        raise MineruParseError("MinerU response is not a valid ZIP", raw_body=_snippet(data)) from exc

    entries: dict[str, bytes] = {}
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts:
                raise MineruParseError(f"unsafe ZIP entry: {info.filename}")
            entries[str(name).replace("\\", "/")] = zf.read(info)

    doc_dir, stem = _locate_document_dir(entries)
    if not stem:
        raise MineruParseError("MinerU ZIP has no markdown document", raw_body=_snippet(data))

    md_key = f"{doc_dir}{stem}.md" if doc_dir else f"{stem}.md"
    md_text = entries.get(md_key, b"").decode("utf-8", errors="replace").strip()
    middle_key = f"{doc_dir}{stem}_middle.json" if doc_dir else f"{stem}_middle.json"
    middle_raw = entries.get(middle_key)
    pdf_info = _pdf_info_from_middle(middle_raw)

    image_bytes: dict[str, bytes] = {}
    prefix = doc_dir + "images/" if doc_dir else "images/"
    for key, blob in entries.items():
        if key.startswith(prefix) and not key.endswith("/"):
            image_bytes[key] = blob

    images_data_uri = _bytes_map_to_data_uris(image_bytes)
    md_with_images, images_used = _inline_markdown_images(md_text, images_data_uri)

    if not pdf_info:
        return [
            MineruPageResult(
                page_index=0,
                markdown_text=md_with_images or None,
                markdown_images=images_used or None,
                page_width=None,
                page_height=None,
            )
        ]

    pages: list[MineruPageResult] = []
    for idx, page in enumerate(pdf_info):
        page_idx = int(page.get("page_idx", idx))
        width, height = _page_size(page)
        text = md_with_images if idx == 0 else None
        page_images = images_used if idx == 0 else None
        pages.append(
            MineruPageResult(
                page_index=page_idx,
                markdown_text=text,
                markdown_images=page_images,
                page_width=width,
                page_height=height,
            )
        )
    return pages


def _parse_mineru_json_bytes(data: bytes) -> list[MineruPageResult]:
    """Parse a JSON ``/file_parse`` body when ``response_format_zip=false``."""
    try:
        parsed: Any = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MineruParseError("MinerU JSON response is not valid UTF-8 JSON", raw_body=_snippet(data)) from exc
    if not isinstance(parsed, dict):
        raise MineruParseError("MinerU JSON response must be an object", raw_body=_snippet(data))

    md_text = ""
    for key in ("md", "markdown", "md_content"):
        val = parsed.get(key)
        if isinstance(val, str) and val.strip():
            md_text = val.strip()
            break

    results = parsed.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            for key in ("md", "markdown"):
                val = first.get(key)
                if isinstance(val, str) and val.strip():
                    md_text = val.strip()
                    break

    if not md_text:
        raise MineruParseError("MinerU JSON response has no markdown field", raw_body=_snippet(data))

    return [
        MineruPageResult(
            page_index=0,
            markdown_text=md_text,
            markdown_images=None,
            page_width=None,
            page_height=None,
        )
    ]


def _locate_document_dir(entries: dict[str, bytes]) -> tuple[str, str | None]:
    """Find ``{dir/}{stem}.md`` and return ``(dir_prefix, stem)``."""
    md_paths = [k for k in entries if k.endswith(".md") and "/images/" not in k]
    if not md_paths:
        return "", None
    md_paths.sort(key=len)
    md_path = md_paths[0]
    pure = PurePosixPath(md_path)
    stem = pure.stem
    parent = pure.parent
    doc_dir = "" if str(parent) == "." else f"{parent.as_posix()}/"
    return doc_dir, stem


def _pdf_info_from_middle(raw: bytes | None) -> list[dict[str, Any]]:
    """Extract ``pdf_info`` list from ``*_middle.json`` bytes."""
    if not raw:
        return []
    try:
        data: Any = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    pdf_info = data.get("pdf_info")
    if isinstance(pdf_info, list):
        return [x for x in pdf_info if isinstance(x, dict)]
    return []


def _page_size(page: dict[str, Any]) -> tuple[int | None, int | None]:
    """Read ``page_size`` as ``[width, height]`` when present."""
    size = page.get("page_size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        try:
            return int(size[0]), int(size[1])
        except (TypeError, ValueError):
            return None, None
    return None, None


def _bytes_map_to_data_uris(images: dict[str, bytes]) -> dict[str, str]:
    """Turn relative image paths into ``data:`` URIs."""
    out: dict[str, str] = {}
    for path, blob in images.items():
        mime, _ = mimetypes.guess_type(path)
        mime = mime or "image/png"
        b64 = base64.standard_b64encode(blob).decode("ascii")
        out[path] = f"data:{mime};base64,{b64}"
    return out


def _inline_markdown_images(
    md_text: str,
    images: dict[str, str],
) -> tuple[str, dict[str, str]]:
    """Replace ``![](path)`` refs with data URIs; return updated md and used images map."""
    if not md_text or not images:
        return md_text, {}
    used: dict[str, str] = {}
    out = md_text
    for path, data_uri in images.items():
        variants = {path, path.lstrip("./"), path.split("/")[-1]}
        parts = path.split("/")
        if len(parts) > 1:
            variants.add("/".join(parts[1:]))
        for variant in variants:
            needle = f"]({variant})"
            if needle in out:
                out = out.replace(needle, f"]({data_uri})")
                used[path] = data_uri
    return out, used


def _snippet(data: bytes, max_len: int = _BODY_SNIPPET_LEN) -> str:
    """Truncate binary/text for error messages."""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = repr(data[:max_len])
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
