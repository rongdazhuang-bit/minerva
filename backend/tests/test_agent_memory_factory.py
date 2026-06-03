"""Tests for memory strategy factory."""

from __future__ import annotations

import pytest

from app.agent.memory.factory import create_memory_strategies


def test_factory_returns_sql_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default sql backend yields SQL strategy classes."""

    monkeypatch.setattr(
        "app.agent.memory.factory.settings.agent_memory_backend", "sql"
    )
    retrieve, persist = create_memory_strategies()
    assert type(retrieve).__name__ == "SqlMemoryRetrieveStrategy"
    assert type(persist).__name__ == "SqlMemoryPersistStrategy"
