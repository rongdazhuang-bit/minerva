"""Tests for agent JSON redaction."""

from __future__ import annotations

from app.agent.infrastructure.redaction import redact_json


def test_redact_strips_secret_like_keys() -> None:
    """Sensitive key names are masked regardless of nesting depth."""

    out = redact_json(
        {"api_key": "sk-xxx", "nested": {"Authorization": "Bearer z", "x": 1}},
        max_bytes=10_000,
    )
    assert out["api_key"] == "***"
    assert out["nested"]["Authorization"] == "***"
    assert out["nested"]["x"] == 1


def test_redact_truncates_large_payload() -> None:
    """Serialized output beyond ``max_bytes`` is replaced with a preview wrapper."""

    out = redact_json({"a": "x" * 5000}, max_bytes=100)
    assert isinstance(out, dict)
    assert out.get("_truncated") is True
