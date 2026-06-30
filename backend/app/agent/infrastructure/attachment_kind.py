"""Attachment MIME whitelist parsing and image vs file kind classification."""

from __future__ import annotations


def allowed_attachment_mime_set(raw: str) -> set[str]:
    """Parse comma-separated MIME whitelist from settings into a lowercase set."""

    return {part.strip().lower() for part in (raw or "").split(",") if part.strip()}


def attachment_kind_from_mime(content_type: str | None) -> str:
    """Return ``image`` when MIME starts with ``image/``; otherwise ``file``."""

    mime = (content_type or "").strip().lower()
    return "image" if mime.startswith("image/") else "file"
