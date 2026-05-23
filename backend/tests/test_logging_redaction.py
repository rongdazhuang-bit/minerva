"""Tests for log payload redaction and truncation."""

from app.core.logging_redaction import redact_for_log


def test_redact_for_log_masks_nested_sensitive_values() -> None:
    """Sensitive keys are masked recursively and case-insensitively."""

    payload = {
        "Authorization": "Bearer secret",
        "user": {
            "password": "pw",
            "items": [{"api_key": "key"}, {"name": "safe"}],
        },
    }

    assert redact_for_log(payload, max_chars=1000) == {
        "Authorization": "[REDACTED]",
        "user": {
            "password": "[REDACTED]",
            "items": [{"api_key": "[REDACTED]"}, {"name": "safe"}],
        },
    }


def test_redact_for_log_truncates_long_strings() -> None:
    """Long strings are shortened and include the original length."""

    result = redact_for_log({"body": "abcdef"}, max_chars=3)

    assert result == {
        "body": {
            "truncated": True,
            "original_length": 6,
            "value": "abc",
        }
    }


def test_redact_for_log_clamps_negative_max_chars() -> None:
    """Negative string limits are treated as zero characters."""

    result = redact_for_log({"body": "abcdef"}, max_chars=-1)

    assert result == {
        "body": {
            "truncated": True,
            "original_length": 6,
            "value": "",
        }
    }


def test_redact_for_log_handles_binary_values() -> None:
    """Bytes are summarized instead of being logged raw."""

    result = redact_for_log({"file": b"abc"}, max_chars=100)

    assert result == {"file": {"binary": True, "length": 3}}


def test_redact_for_log_masks_common_sensitive_key_variants() -> None:
    """Sensitive key variants are matched across casing and separators."""

    payload = {
        "client_secret": "a",
        "secret_key": "b",
        "private_key": "c",
        "id_token": "d",
        "accessToken": "e",
        "apiKey": "f",
        "x-api-key": "g",
        "monkey": "safe",
    }

    assert redact_for_log(payload, max_chars=100) == {
        "client_secret": "[REDACTED]",
        "secret_key": "[REDACTED]",
        "private_key": "[REDACTED]",
        "id_token": "[REDACTED]",
        "accessToken": "[REDACTED]",
        "apiKey": "[REDACTED]",
        "x-api-key": "[REDACTED]",
        "monkey": "safe",
    }


def test_redact_for_log_preserves_tuple_shape() -> None:
    """Tuples are recursively redacted without changing container type."""

    result = redact_for_log(({"password": "pw"}, {"name": "safe"}), max_chars=100)

    assert result == ({"password": "[REDACTED]"}, {"name": "safe"})
    assert isinstance(result, tuple)
