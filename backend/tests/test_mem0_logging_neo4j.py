"""Tests for mem0 Neo4j request/response logging."""

from __future__ import annotations

import logging

from app.agent.memory.mem0.logging_neo4j import (
    LoggingNeo4jGraphWrapper,
    build_neo4j_request_fields,
    format_neo4j_request_message,
    format_neo4j_response_message,
    log_neo4j_request,
    log_neo4j_response,
    summarize_neo4j_results,
    wrap_mem0_memory_graph_with_logging,
    wrap_neo4j_graph_with_logging,
)


class _FakeNeo4jGraph:
    """Minimal Neo4jGraph stand-in for logging tests."""

    url = "neo4j://127.0.0.1:7687"
    database = "neo4j"

    def __init__(self) -> None:
        """Track query invocations."""

        self.calls: list[tuple[str, dict | None]] = []

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Return deterministic rows and record the call."""

        self.calls.append((cypher, params))
        return [{"n": {"name": "Alice", "user_id": params.get("user_id") if params else None}}]


class _FakeMemoryGraph:
    """Minimal mem0 MemoryGraph stand-in."""

    def __init__(self) -> None:
        """Initialize with an inner Neo4j graph."""

        self.graph = _FakeNeo4jGraph()


class _FakeMemory:
    """Minimal mem0 Memory stand-in with graph enabled."""

    def __init__(self) -> None:
        """Attach a graph memory instance."""

        self.graph = _FakeMemoryGraph()


def test_build_neo4j_request_fields_includes_cypher_and_params() -> None:
    """Request logs include Cypher and redacted params."""

    fields = build_neo4j_request_fields(
        cypher="MATCH (n) WHERE n.user_id = $user_id RETURN n",
        params={"user_id": "ws-1", "password": "secret"},
    )
    assert "MATCH" in fields["cypher"]
    assert fields["params"]["user_id"] == "ws-1"
    assert fields["params"]["password"] != "secret"


def test_format_neo4j_messages_use_plain_text_not_json() -> None:
    """Neo4j log messages are plain key=value strings."""

    request = format_neo4j_request_message(
        endpoint="neo4j://127.0.0.1:7687 db=neo4j",
        cypher="RETURN 1",
        params={"user_id": "ws-1"},
    )
    response = format_neo4j_response_message(
        endpoint="neo4j://127.0.0.1:7687 db=neo4j",
        results=[{"n": {"name": "Bob"}}],
    )
    assert request.startswith("mem0 neo4j request ")
    assert "cypher='RETURN 1'" in request or "cypher=RETURN 1" in request
    assert "params={user_id=ws-1}" in request
    assert response.startswith("mem0 neo4j response ")
    assert "row_count=1" in response
    assert '"user_id"' not in request


def test_summarize_neo4j_results_limits_row_preview() -> None:
    """Response summaries include row count and only preview rows."""

    rows = [{"id": index} for index in range(8)]
    summary = summarize_neo4j_results(rows)
    assert summary["row_count"] == 8
    assert summary["rows_truncated"] == 3
    assert len(summary["rows"]) == 5


def test_logging_wrapper_emits_request_and_response(caplog) -> None:
    """Wrapper logs one request/response pair per query call."""

    caplog.set_level(logging.INFO)
    wrapped = wrap_neo4j_graph_with_logging(_FakeNeo4jGraph())
    assert isinstance(wrapped, LoggingNeo4jGraphWrapper)
    rows = wrapped.query("RETURN 1 AS n", params={"user_id": "ws-1"})
    assert rows[0]["n"]["name"] == "Alice"
    messages = [record.message for record in caplog.records]
    assert any("mem0 neo4j request" in message for message in messages)
    assert any("mem0 neo4j response" in message for message in messages)
    assert all("{" not in message or "user_id=ws-1" in message for message in messages)


def test_wrap_mem0_memory_graph_with_logging_replaces_inner_graph() -> None:
    """Memory-level helper wraps ``graph.graph`` once."""

    memory = _FakeMemory()
    original = memory.graph.graph
    wrap_mem0_memory_graph_with_logging(memory)
    assert isinstance(memory.graph.graph, LoggingNeo4jGraphWrapper)
    assert memory.graph.graph._inner is original
    wrap_mem0_memory_graph_with_logging(memory)
    assert isinstance(memory.graph.graph, LoggingNeo4jGraphWrapper)


def test_log_helpers_include_endpoint_and_body(caplog) -> None:
    """Standalone log helpers include endpoint and plain-text fields."""

    caplog.set_level(logging.INFO)
    inner = _FakeNeo4jGraph()
    log_neo4j_request(
        inner=inner,
        cypher="MATCH (n) RETURN n LIMIT 1",
        params={"user_id": "ws-1"},
    )
    log_neo4j_response(inner=inner, results=[{"n": {"name": "Bob"}}], extra={"status": "ok"})
    joined = "\n".join(record.message for record in caplog.records)
    assert "neo4j://127.0.0.1:7687" in joined
    assert "db=neo4j" in joined
    assert "row_count=1" in joined
    assert "status=ok" in joined
