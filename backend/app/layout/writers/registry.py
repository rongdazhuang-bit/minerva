"""Resolve layout writers by normalized file extension."""

from __future__ import annotations

from app.layout.writers.pdf_writer import PdfWriter


def get_layout_writer(ext: str) -> object:
    """Return a layout writer for a normalized extension."""

    key = ext.lower().lstrip(".")
    if key == "pdf":
        return PdfWriter()
    raise KeyError(f"No layout writer registered for extension: {ext}")
