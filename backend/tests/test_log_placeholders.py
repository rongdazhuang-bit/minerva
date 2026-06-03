"""Tests for SLF4J-style {} log placeholders."""

from __future__ import annotations

from app.core.log_placeholders import PlaceholderResult, format_placeholders


def test_format_placeholders_zero_args() -> None:
    """Messages without placeholders pass through unchanged."""

    result = format_placeholders("database bootstrap started")

    assert result == PlaceholderResult(
        message="database bootstrap started",
        matched=True,
        expected=0,
        provided=0,
    )


def test_format_placeholders_single_arg() -> None:
    """One {} is replaced with a formatted value."""

    result = format_placeholders("validate token: {}", "abc-123")

    assert result.matched is True
    assert result.message == "validate token: abc-123"


def test_format_placeholders_multiple_args() -> None:
    """Multiple {} placeholders are replaced in order."""

    result = format_placeholders("a {} b {}", 1, 2)

    assert result.matched is True
    assert result.message == "a 1 b 2"


def test_format_placeholders_escapes_braces() -> None:
    """Doubled braces render literal brace characters."""

    result = format_placeholders("{{literal}} and {}", "x")

    assert result.matched is True
    assert result.message == "{literal} and x"


def test_format_placeholders_quotes_strings_with_spaces() -> None:
    """String values with whitespace are repr-quoted like format_log_value."""

    result = format_placeholders("user={}", "hello world")

    assert result.matched is True
    assert result.message == "user='hello world'"


def test_format_placeholders_too_few_args() -> None:
    """Too few args returns the original template and matched=False."""

    result = format_placeholders("a {} b {}", 1)

    assert result.matched is False
    assert result.expected == 2
    assert result.provided == 1
    assert result.message == "a {} b {}"


def test_format_placeholders_too_many_args() -> None:
    """Too many args returns the original template and matched=False."""

    result = format_placeholders("only {}", 1, 2)

    assert result.matched is False
    assert result.expected == 1
    assert result.provided == 2
    assert result.message == "only {}"
