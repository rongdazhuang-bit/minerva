"""Tests for agent memory backend settings validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_agent_memory_backend_defaults_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default backend is sql when AGENT_MEMORY_BACKEND is unset."""

    monkeypatch.delenv("AGENT_MEMORY_BACKEND", raising=False)
    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "sql")
    s = Settings()
    assert s.agent_memory_backend == "sql"


def test_mem0_backend_requires_pg_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """mem0 backend without PG connection settings fails validation."""

    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "mem0")
    monkeypatch.delenv("MEM0_DATABASE_URL", raising=False)
    monkeypatch.setenv("MEM0_DATABASE_URL", "")
    monkeypatch.delenv("MEM0_PG_HOST", raising=False)
    monkeypatch.setenv("MEM0_PG_HOST", "")
    monkeypatch.delenv("MEM0_PG_USER", raising=False)
    monkeypatch.setenv("MEM0_PG_USER", "")
    with pytest.raises(ValidationError):
        Settings()


def test_mem0_backend_with_database_url_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """mem0 backend accepts MEM0_DATABASE_URL alone."""

    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "mem0")
    monkeypatch.setenv(
        "MEM0_DATABASE_URL",
        "postgresql://minerva:minerva@127.0.0.1:5432/minerva_memory",
    )
    monkeypatch.setenv("MEM0_GRAPH_ENABLED", "false")
    s = Settings()
    assert s.agent_memory_backend == "mem0"


def test_mem0_graph_requires_neo4j(monkeypatch: pytest.MonkeyPatch) -> None:
    """mem0 with graph enabled requires Neo4j URL and password."""

    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "mem0")
    monkeypatch.setenv(
        "MEM0_DATABASE_URL",
        "postgresql://minerva:minerva@127.0.0.1:5432/minerva_memory",
    )
    monkeypatch.setenv("MEM0_GRAPH_ENABLED", "true")
    monkeypatch.setenv("MEM0_NEO4J_URL", "")
    with pytest.raises(ValidationError):
        Settings()
