"""Redact secrets and bound JSON payload size before logging or persisting snapshots."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY = re.compile(r"(api_?key|authorization|password|secret|token|bearer)", re.I)


def redact_json(value: Any, *, max_bytes: int) -> Any:
    """Return a deep-copied structure with sensitive keys masked and serialized size capped."""

    def _walk(v: Any) -> Any:
        if isinstance(v, dict):
            out: dict[str, Any] = {}
            for k, x in v.items():
                if isinstance(k, str) and _SENSITIVE_KEY.search(k):
                    out[k] = "***"
                else:
                    out[k] = _walk(x)
            return out
        if isinstance(v, list):
            return [_walk(i) for i in v]
        return v

    cleaned = _walk(value)
    try:
        import orjson

        raw = orjson.dumps(cleaned)
    except Exception:  # noqa: BLE001
        raw = str(cleaned).encode("utf-8", errors="replace")
    if len(raw) > max_bytes:
        return {"_truncated": True, "_max_bytes": max_bytes, "_preview": raw[:max_bytes].decode("utf-8", errors="replace")}
    return cleaned
