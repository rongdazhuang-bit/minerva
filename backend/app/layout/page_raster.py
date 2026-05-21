"""Render PDF/image pages to PNG rasters and upload to workspace S3."""

from __future__ import annotations

import uuid
from pathlib import Path

import fitz
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.s3.service.s3_file_service import S3FileService


def _render_pdf_page_pngs(source_bytes: bytes, *, dpi: int = 144) -> list[bytes]:
    """Rasterize each PDF page to PNG bytes."""

    doc = fitz.open(stream=source_bytes, filetype="pdf")
    out: list[bytes] = []
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


def _image_bytes_to_png(source_bytes: bytes, *, suffix: str) -> bytes:
    """Normalize one image file to PNG bytes via PyMuPDF."""

    doc = fitz.open(stream=source_bytes, filetype=suffix.lstrip("."))
    try:
        pix = doc[0].get_pixmap(alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def rasterize_source_file(source_bytes: bytes, *, file_name: str | None) -> list[bytes]:
    """
    Produce one PNG per page for PDF inputs, or a single page for raster images.

    Falls back to a single-page raster when format is unknown.
    """

    name = (file_name or "").lower()
    if name.endswith(".pdf"):
        return _render_pdf_page_pngs(source_bytes)
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        if name.endswith(ext):
            return [_image_bytes_to_png(source_bytes, suffix=ext)]
    try:
        return _render_pdf_page_pngs(source_bytes)
    except Exception:
        return [_image_bytes_to_png(source_bytes, suffix=".png")]


async def upload_page_rasters(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
    page_pngs: list[bytes],
) -> dict[int, str]:
    """Upload page PNGs and return ``page_index -> object_key``."""

    prefix = settings.layout_page_raster_prefix.strip().rstrip("/")
    s3 = S3FileService(session=session)
    keys: dict[int, str] = {}
    for idx, png in enumerate(page_pngs):
        file_name = f"{ocr_file_id}-p{idx}.png"
        result = await s3.upload_file(
            workspace_id=workspace_id,
            module_prefix=prefix,
            file_name=file_name,
            payload=png,
            content_type="image/png",
        )
        keys[idx] = result.object_key
    return keys
