"""Request and task scoped logging context helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

# Request identifier bound to the current async/thread execution context.
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# Task identifier bound to the current async/thread execution context.
_task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)
# Process category bound to the current async/thread execution context.
_process_type_var: ContextVar[str | None] = ContextVar("process_type", default=None)
# Optional chat/session identifier propagated from ``X-Chat-Id``.
_x_chat_id_var: ContextVar[str | None] = ContextVar("x_chat_id", default=None)
# Distributed trace identifier; falls back to ``request_id`` in formatters when unset.
_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def set_logging_context(
    *,
    request_id: str | None = None,
    task_id: str | None = None,
    process_type: str | None = None,
    x_chat_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Set non-empty logging context values for the current execution context."""

    if request_id is not None:
        _request_id_var.set(request_id)
    if task_id is not None:
        _task_id_var.set(task_id)
    if process_type is not None:
        _process_type_var.set(process_type)
    if x_chat_id is not None:
        _x_chat_id_var.set(x_chat_id)
    if trace_id is not None:
        _trace_id_var.set(trace_id)


def clear_logging_context() -> None:
    """Clear request and task scoped values for the current execution context."""

    _request_id_var.set(None)
    _task_id_var.set(None)
    _process_type_var.set(None)
    _x_chat_id_var.set(None)
    _trace_id_var.set(None)


def get_logging_context() -> dict[str, str]:
    """Return the currently active logging context without empty fields."""

    values = {
        "request_id": _request_id_var.get(),
        "task_id": _task_id_var.get(),
        "process_type": _process_type_var.get(),
        "x_chat_id": _x_chat_id_var.get(),
        "trace_id": _trace_id_var.get(),
    }
    return {key: value for key, value in values.items() if value}


@contextmanager
def use_logging_context(
    *,
    request_id: str | None = None,
    task_id: str | None = None,
    process_type: str | None = None,
    x_chat_id: str | None = None,
    trace_id: str | None = None,
) -> Iterator[None]:
    """Temporarily apply logging context and restore previous values on exit."""

    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    if request_id is not None:
        tokens.append((_request_id_var, _request_id_var.set(request_id)))
    if task_id is not None:
        tokens.append((_task_id_var, _task_id_var.set(task_id)))
    if process_type is not None:
        tokens.append((_process_type_var, _process_type_var.set(process_type)))
    if x_chat_id is not None:
        tokens.append((_x_chat_id_var, _x_chat_id_var.set(x_chat_id)))
    if trace_id is not None:
        tokens.append((_trace_id_var, _trace_id_var.set(trace_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
