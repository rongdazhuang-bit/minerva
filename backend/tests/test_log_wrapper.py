"""Tests for MinervaLogger wrapper and get_logger factory."""

from __future__ import annotations

import logging

import pytest

from app.core.log import MinervaLogger, get_logger


@pytest.fixture(autouse=True)
def _reset_logger_cache() -> None:
    """Ensure each test gets a fresh wrapper cache."""

    import app.core.log as log_module

    log_module._LOGGER_CACHE.clear()
    yield
    log_module._LOGGER_CACHE.clear()


def test_get_logger_returns_cached_wrapper() -> None:
    """Same name returns the same MinervaLogger instance."""

    first = get_logger("app.test.cache")
    second = get_logger("app.test.cache")

    assert first is second
    assert isinstance(first, MinervaLogger)
    assert first.name == "app.test.cache"


def test_info_replaces_placeholders(caplog: pytest.LogCaptureFixture) -> None:
    """info() replaces {} placeholders before delegating to stdlib."""

    caplog.set_level(logging.INFO)
    log = get_logger("app.test.placeholder")

    log.info("validate token: {}", "tok-1", event="auth.validate")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "validate token: tok-1"
    assert record.event == "auth.validate"
    assert record.levelname == "INFO"


def test_kwargs_override_extra(caplog: pytest.LogCaptureFixture) -> None:
    """Keyword fields override duplicate keys from extra."""

    caplog.set_level(logging.INFO)
    log = get_logger("app.test.merge")

    log.info("retry", extra={"component": "llm", "attempts": 1}, attempts=3)

    record = caplog.records[0]
    assert record.component == "llm"
    assert record.attempts == 3


def test_exc_info_passthrough(caplog: pytest.LogCaptureFixture) -> None:
    """exc_info is forwarded to stdlib logging."""

    caplog.set_level(logging.ERROR)
    log = get_logger("app.test.exc_info")

    try:
        raise ValueError("boom")
    except ValueError:
        log.error("failed", exc_info=True)

    record = caplog.records[0]
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError


def test_warn_aliases_warning(caplog: pytest.LogCaptureFixture) -> None:
    """warn() emits WARNING level records."""

    caplog.set_level(logging.WARNING)
    log = get_logger("app.test.warn")

    log.warn("slow path")

    assert caplog.records[0].levelname == "WARNING"


def test_exception_sets_exc_info(caplog: pytest.LogCaptureFixture) -> None:
    """exception() defaults exc_info=True."""

    caplog.set_level(logging.ERROR)
    log = get_logger("app.test.exception")

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("failed hard")

    record = caplog.records[0]
    assert record.levelname == "ERROR"
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError


def test_mismatch_emits_internal_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Placeholder mismatch keeps the template and logs an internal warning."""

    caplog.set_level(logging.INFO)
    log = get_logger("app.test.mismatch")

    log.info("a {} b {}", 1)

    assert len(caplog.records) == 2
    assert caplog.records[0].levelname == "WARNING"
    assert "placeholder mismatch" in caplog.records[0].message
    assert caplog.records[1].levelname == "INFO"
    assert caplog.records[1].message == "a {} b {}"


def test_stacklevel_points_to_caller() -> None:
    """Delegated records use the business caller line number."""

    log = get_logger("app.test.stacklevel")
    underlying = log._underlying
    captured: list[logging.LogRecord] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _CaptureHandler()
    underlying.addHandler(handler)
    underlying.setLevel(logging.INFO)
    try:

        def _emit_from_helper() -> None:
            log.info("helper line")

        _emit_from_helper()
    finally:
        underlying.removeHandler(handler)

    assert captured
    assert captured[0].lineno == _emit_from_helper.__code__.co_firstlineno + 1
