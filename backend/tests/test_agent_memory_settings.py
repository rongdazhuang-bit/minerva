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


def test_mem0_backend_requires_mem0ai_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mem0 backend fails fast with install hint when mem0ai is not importable."""

    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "mem0")
    monkeypatch.setenv(
        "MEM0_DATABASE_URL",
        "postgresql://minerva:minerva@127.0.0.1:5432/minerva_memory",
    )
    monkeypatch.setenv("MEM0_GRAPH_ENABLED", "false")

    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "mem0":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "mem0ai" in str(exc_info.value).lower()


def test_mem0_backend_requires_spacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """mem0 backend fails fast when spaCy is not installed."""

    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "mem0")
    monkeypatch.setenv(
        "MEM0_DATABASE_URL",
        "postgresql://minerva:minerva@127.0.0.1:5432/minerva_memory",
    )
    monkeypatch.setenv("MEM0_GRAPH_ENABLED", "false")

    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "spacy":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "spacy" in str(exc_info.value).lower()


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
