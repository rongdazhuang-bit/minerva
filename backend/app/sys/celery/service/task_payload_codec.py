"""Shared payload normalization for run-now dispatch and beat schedule build."""

from __future__ import annotations

from typing import Any


def normalize_task_args(value: Any) -> list[Any]:
    """Normalize ``args_json`` so dict/list/None semantics stay stable across paths."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_task_kwargs(value: Any) -> dict[str, Any]:
    """Normalize ``kwargs_json`` to Celery keyword-argument mapping."""

    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    raise TypeError("kwargs_json must be a dict or null")
