"""Tests for Celery logging context propagation into task headers."""

import pytest

from app.celery_app import _merge_task_context_headers
from app.core.logging_context import clear_logging_context, use_logging_context


@pytest.fixture(autouse=True)
def isolate_logging_context():
    """Ensure each test starts and ends with an empty logging context."""

    clear_logging_context()
    try:
        yield
    finally:
        clear_logging_context()


def test_merge_task_context_headers_uses_context_when_missing() -> None:
    """Current logging context is injected into Celery headers when absent."""

    with use_logging_context(
        request_id="req-1",
        trace_id="trace-1",
        x_chat_id="chat-1",
    ):
        headers = _merge_task_context_headers({"existing": "value"})

    assert headers == {
        "existing": "value",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "x_chat_id": "chat-1",
    }


def test_merge_task_context_headers_preserves_explicit_values() -> None:
    """Explicit Celery headers win over current logging context."""

    with use_logging_context(
        request_id="req-context",
        trace_id="trace-context",
        x_chat_id="chat-context",
    ):
        headers = _merge_task_context_headers(
            {
                "request_id": "req-explicit",
                "trace_id": "trace-explicit",
                "x_chat_id": "chat-explicit",
            }
        )

    assert headers["request_id"] == "req-explicit"
    assert headers["trace_id"] == "trace-explicit"
    assert headers["x_chat_id"] == "chat-explicit"
