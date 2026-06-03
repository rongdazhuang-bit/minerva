"""Request/response logging wrapper for mem0 Neo4j graph queries."""

from __future__ import annotations

from app.core.log import get_logger
from typing import Any

from app.core.logging_redaction import redact_for_log
from app.core.logging_text import format_log_kv
from app.llm.strategies.http_common import text_for_log

log = get_logger(__name__)

_LOG_VALUE_MAX_CHARS = 500
_LOG_ROW_PREVIEW = 5
_LOG_DICT_KEYS_PREVIEW = 20


def wrap_neo4j_graph_with_logging(inner: Any) -> Any:
    """Return ``inner`` wrapped with Neo4j Cypher request/response logs."""

    if inner is None or isinstance(inner, LoggingNeo4jGraphWrapper):
        return inner
    return LoggingNeo4jGraphWrapper(inner)


def neo4j_endpoint_for(inner: Any) -> str:
    """Resolve Neo4j Bolt URL and database name for log lines."""

    url = getattr(inner, "url", None) or getattr(inner, "_url", None) or "(unknown)"
    database = getattr(inner, "database", None) or getattr(inner, "_database", None) or "neo4j"
    return f"{url} db={database}"


def build_neo4j_request_fields(*, cypher: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Build log-safe Neo4j request fields for plain-text messages."""

    fields: dict[str, Any] = {"cypher": text_for_log((cypher or "").strip())}
    if params:
        fields["params"] = redact_for_log(params, max_chars=_LOG_VALUE_MAX_CHARS)
    return fields


def _summarize_log_value(value: Any, *, depth: int = 0) -> Any:
    """Summarize one Neo4j result value without dumping large nested payloads."""

    if depth > 3:
        return "..."
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return text_for_log(value) if len(value) > _LOG_VALUE_MAX_CHARS else value
    if isinstance(value, dict):
        items = list(value.items())[:_LOG_DICT_KEYS_PREVIEW]
        summarized = {
            key: _summarize_log_value(item, depth=depth + 1) for key, item in items
        }
        if len(value) > _LOG_DICT_KEYS_PREVIEW:
            summarized["truncated_keys"] = len(value) - _LOG_DICT_KEYS_PREVIEW
        return summarized
    if isinstance(value, (list, tuple)):
        preview = [_summarize_log_value(item, depth=depth + 1) for item in value[:_LOG_ROW_PREVIEW]]
        if len(value) > _LOG_ROW_PREVIEW:
            return {"items": preview, "truncated": len(value) - _LOG_ROW_PREVIEW}
        return preview
    return text_for_log(str(value))


def summarize_neo4j_results(results: Any) -> dict[str, Any]:
    """Summarize Neo4j query results for logs without dumping full graph payloads."""

    if results is None:
        return {"row_count": 0, "rows": []}
    if isinstance(results, list):
        rows = [_summarize_log_value(row) for row in results[:_LOG_ROW_PREVIEW]]
        body: dict[str, Any] = {"row_count": len(results), "rows": rows}
        if len(results) > _LOG_ROW_PREVIEW:
            body["rows_truncated"] = len(results) - _LOG_ROW_PREVIEW
        return body
    return {"result_preview": _summarize_log_value(results)}


def format_neo4j_request_message(*, endpoint: str, cypher: str, params: dict[str, Any] | None) -> str:
    """Build one plain-text Neo4j request log message."""

    fields = build_neo4j_request_fields(cypher=cypher, params=params)
    details = format_log_kv(endpoint=endpoint, **fields)
    return f"mem0 neo4j request {details}" if details else "mem0 neo4j request"


def format_neo4j_response_message(
    *,
    endpoint: str,
    results: Any,
    extra: dict[str, Any] | None = None,
) -> str:
    """Build one plain-text Neo4j response log message."""

    summary = summarize_neo4j_results(results)
    fields: dict[str, Any] = {
        "endpoint": endpoint,
        "row_count": summary.get("row_count", 0),
    }
    if summary.get("rows"):
        fields["rows"] = summary["rows"]
    if summary.get("rows_truncated") is not None:
        fields["rows_truncated"] = summary["rows_truncated"]
    if summary.get("result_preview") is not None:
        fields["result_preview"] = summary["result_preview"]
    if extra:
        fields.update(extra)
    details = format_log_kv(**fields)
    return f"mem0 neo4j response {details}" if details else "mem0 neo4j response"


def log_neo4j_request(*, inner: Any, cypher: str, params: dict[str, Any] | None) -> None:
    """Emit INFO log for one Neo4j Cypher request."""

    log.info(format_neo4j_request_message(
        endpoint=neo4j_endpoint_for(inner),
        cypher=cypher,
        params=params,
    ))


def log_neo4j_response(*, inner: Any, results: Any, extra: dict[str, Any] | None = None) -> None:
    """Emit INFO log for one Neo4j Cypher response summary."""

    log.info(format_neo4j_response_message(
        endpoint=neo4j_endpoint_for(inner),
        results=results,
        extra=extra,
    ))


def wrap_mem0_memory_graph_with_logging(memory: Any) -> None:
    """Wrap mem0 ``Memory.graph.graph`` (langchain Neo4jGraph) when graph store is enabled."""

    graph_memory = getattr(memory, "graph", None)
    if graph_memory is None:
        return
    inner_graph = getattr(graph_memory, "graph", None)
    if inner_graph is None or isinstance(inner_graph, LoggingNeo4jGraphWrapper):
        return
    graph_memory.graph = wrap_neo4j_graph_with_logging(inner_graph)


class LoggingNeo4jGraphWrapper:
    """Delegate to langchain Neo4jGraph while logging Cypher request/response summaries."""

    def __init__(self, inner: Any) -> None:
        """Wrap an existing Neo4jGraph (or compatible) instance."""

        self._inner = inner

    def query(self, *args: Any, **kwargs: Any) -> Any:
        """Run Cypher via the inner graph and log request/response summaries."""

        cypher = str(args[0]) if args else str(kwargs.get("query", ""))
        params = kwargs.get("params")
        if params is None and len(args) > 1 and isinstance(args[1], dict):
            params = args[1]
        log_neo4j_request(inner=self._inner, cypher=cypher, params=params)
        try:
            result = self._inner.query(*args, **kwargs)
        except Exception as exc:
            log_neo4j_response(
                inner=self._inner,
                results=None,
                extra={"error": text_for_log(str(exc))},
            )
            raise
        log_neo4j_response(inner=self._inner, results=result)
        return result

    def __getattr__(self, name: str) -> Any:
        """Forward unknown attributes to the wrapped Neo4j graph."""

        return getattr(self._inner, name)
