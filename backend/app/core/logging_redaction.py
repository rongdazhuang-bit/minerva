"""Sanitize values before they are written to application logs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# Field name parts whose values must never be emitted to logs.
SENSITIVE_FIELD_PARTS = frozenset(
    {
        "password",
        "token",
        "authorization",
        "key",
        "secret",
        "jwt",
        "captcha",
        "credential",
        "cookie",
        "set-cookie",
    }
)


def _key_parts(key: object) -> list[str]:
    """Split a mapping key into normalized name parts for sensitivity checks."""

    key_text = str(key).strip()
    camel_split_text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key_text)
    return [
        part.lower()
        for part in re.split(r"[^A-Za-z0-9]+", camel_split_text)
        if part
    ]


def _is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key should have its value masked."""

    return any(part in SENSITIVE_FIELD_PARTS for part in _key_parts(key))


def _truncate_text(value: str, max_chars: int) -> str | dict[str, Any]:
    """Return text unchanged or a structured truncation summary."""

    safe_max_chars = max(max_chars, 0)
    if len(value) <= safe_max_chars:
        return value
    return {
        "truncated": True,
        "original_length": len(value),
        "value": value[:safe_max_chars],
    }


def redact_for_log(value: Any, *, max_chars: int) -> Any:
    """Recursively redact sensitive values and truncate oversized payloads."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if _is_sensitive_key(key)
            else redact_for_log(item, max_chars=max_chars)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_for_log(item, max_chars=max_chars) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_for_log(item, max_chars=max_chars) for item in value)
    if isinstance(value, bytes):
        return {"binary": True, "length": len(value)}
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    return value
