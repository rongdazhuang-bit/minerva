"""Sanitize text before PostgreSQL TEXT / JSONB persistence."""

from __future__ import annotations

import re
from typing import Any

# Lone UTF-16 surrogates are invalid in PostgreSQL UTF-8 text.
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def sanitize_postgres_text(value: str | None) -> str | None:
    """Remove null bytes and surrogate code points that asyncpg/PostgreSQL reject."""

    if value is None:
        return None
    cleaned = value.replace("\x00", "")
    cleaned = _SURROGATE_RE.sub("", cleaned)
    return cleaned


def sanitize_postgres_json(value: Any) -> Any:
    """Recursively sanitize all strings inside JSON-serializable trees (e.g. JSONB)."""

    if value is None:
        return None
    if isinstance(value, str):
        return sanitize_postgres_text(value)
    if isinstance(value, dict):
        return {k: sanitize_postgres_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_postgres_json(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize_postgres_json(v) for v in value]
    return value
