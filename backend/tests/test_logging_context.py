"""Tests for request/task logging context helpers."""

from collections.abc import Iterator

import pytest

from app.core.logging_context import (
    clear_logging_context,
    get_logging_context,
    set_logging_context,
    use_logging_context,
)


@pytest.fixture(autouse=True)
def isolate_logging_context() -> Iterator[None]:
    """Clear logging context before and after each test."""

    clear_logging_context()
    try:
        yield
    finally:
        clear_logging_context()


def test_set_and_clear_logging_context() -> None:
    """Context fields are visible after set and removed after clear."""

    set_logging_context(
        request_id="req-1",
        task_id="task-1",
        process_type="api",
        x_chat_id="chat-1",
        trace_id="trace-1",
    )

    assert get_logging_context() == {
        "request_id": "req-1",
        "task_id": "task-1",
        "process_type": "api",
        "x_chat_id": "chat-1",
        "trace_id": "trace-1",
    }

    clear_logging_context()

    assert get_logging_context() == {}


def test_use_logging_context_restores_previous_values() -> None:
    """Nested context usage restores the previous values after exit."""

    set_logging_context(request_id="outer", process_type="api")

    with use_logging_context(request_id="inner", task_id="task-2"):
        assert get_logging_context() == {
            "request_id": "inner",
            "task_id": "task-2",
            "process_type": "api",
        }

    assert get_logging_context() == {
        "request_id": "outer",
        "process_type": "api",
    }
