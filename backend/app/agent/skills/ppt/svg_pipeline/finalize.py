"""Finalize SVG page files: discover pages and inline external image references."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

_XLINK_NS = "http://www.w3.org/1999/xlink"
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}


def _local_tag(tag: str) -> str:
    """Return the XML local name without namespace prefix."""

    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _get_href(element: ET.Element) -> str | None:
    """Read xlink:href or href from an SVG element."""

    href = element.get(f"{{{_XLINK_NS}}}href") or element.get("href")
    if href is None:
        return None
    href = href.strip()
    return href or None


def _is_external_href(href: str) -> bool:
    """Return True when href points at a copyable relative file reference."""

    if not href or href.startswith("#"):
        return False
    if href.startswith("data:"):
        return False
    parsed = urlparse(href)
    if parsed.scheme in {"http", "https", "file"}:
        return False
    return True


def _collect_image_hrefs(svg_path: Path) -> list[str]:
    """Parse an SVG file and collect external image href values."""

    try:
        tree = ET.parse(svg_path)
    except (ET.ParseError, OSError):
        return []
    hrefs: list[str] = []
    for element in tree.iter():
        if _local_tag(element.tag) != "image":
            continue
        href = _get_href(element)
        if href and _is_external_href(href):
            hrefs.append(unquote(href))
    return hrefs


def _copy_href_asset(
    svg_path: Path,
    href: str,
    *,
    svg_dir: Path,
    assets_dir: Path | None,
) -> None:
    """Copy a relative image referenced by an SVG into the assets directory."""

    source = (svg_path.parent / href).resolve()
    if not source.is_file():
        return
    if source.suffix.lower() not in _IMAGE_SUFFIXES:
        return

    target_dir = assets_dir if assets_dir is not None else svg_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / Path(href).name
    if destination.resolve() == source:
        return
    if not destination.is_file():
        shutil.copy2(source, destination)


def finalize_svg_pages(svg_dir: Path, *, assets_dir: Path | None = None) -> list[Path]:
    """Return sorted page SVG paths; copy external href images into assets_dir if needed."""

    if not svg_dir.is_dir():
        return []

    page_paths = sorted(svg_dir.glob("page_*.svg"))
    if assets_dir is not None:
        assets_dir.mkdir(parents=True, exist_ok=True)

    for svg_path in page_paths:
        for href in _collect_image_hrefs(svg_path):
            _copy_href_asset(svg_path, href, svg_dir=svg_dir, assets_dir=assets_dir)

    return page_paths
