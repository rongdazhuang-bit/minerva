"""Sanitize values before they are written to application logs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Field names whose values must never be emitted to logs.
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "secret",
        "jwt",
        "captcha",
        "credential",
        "cookie",
        "set-cookie",
    }
)


def _is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key should have its value masked."""

    return str(key).strip().lower() in SENSITIVE_FIELD_NAMES


def _truncate_text(value: str, max_chars: int) -> str | dict[str, Any]:
    """Return text unchanged or a structured truncation summary."""

    if len(value) <= max_chars:
        return value
    return {
        "truncated": True,
        "original_length": len(value),
        "value": value[:max_chars],
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
        return [redact_for_log(item, max_chars=max_chars) for item in value]
    if isinstance(value, bytes):
        return {"binary": True, "length": len(value)}
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    return value
