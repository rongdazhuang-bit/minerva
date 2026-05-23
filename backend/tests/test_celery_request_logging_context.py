"""Tests for Celery request_id propagation into task logging context."""

import pytest

from app.celery_app import _merge_request_id_header
from app.core.logging_context import clear_logging_context, use_logging_context


@pytest.fixture(autouse=True)
def isolate_logging_context():
    """Ensure each test starts and ends with an empty logging context."""

    clear_logging_context()
    try:
        yield
    finally:
        clear_logging_context()


def test_merge_request_id_header_uses_context_when_missing() -> None:
    """Current request_id is injected into Celery headers when absent."""

    with use_logging_context(request_id="req-1"):
        headers = _merge_request_id_header({"existing": "value"})

    assert headers == {"existing": "value", "request_id": "req-1"}


def test_merge_request_id_header_preserves_explicit_value() -> None:
    """Explicit Celery request_id header wins over context."""

    with use_logging_context(request_id="req-context"):
        headers = _merge_request_id_header({"request_id": "req-explicit"})

    assert headers["request_id"] == "req-explicit"
