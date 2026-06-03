"""Request/response logging wrapper for mem0 embedder calls."""

from __future__ import annotations

from typing import Any, Literal

from app.core.log import get_logger
from app.core.logging_text import format_log_kv
from app.llm.strategies.http_common import text_for_log

log = get_logger(__name__)

def wrap_embedder_with_logging(inner: Any) -> Any:
    """Return ``inner`` wrapped with embedder HTTP-style request/response logs."""

    if inner is None or isinstance(inner, LoggingEmbedderWrapper):
        return inner
    return LoggingEmbedderWrapper(inner)


def embeddings_url_for(inner: Any) -> str:
    """Resolve OpenAI-compatible ``/embeddings`` URL from a mem0 embedder instance."""

    config = getattr(inner, "config", None)
    base = (
        getattr(config, "openai_base_url", None)
        or getattr(config, "ollama_base_url", None)
        or getattr(config, "huggingface_base_url", None)
        or getattr(config, "lmstudio_base_url", None)
        or ""
    )
    base = str(base).strip().rstrip("/")
    if not base:
        return "(unknown)/embeddings"
    if base.endswith("/embeddings"):
        return base
    if base.endswith("/v1"):
        return f"{base}/embeddings"
    return f"{base}/v1/embeddings"


def build_embedder_request_body(
    *,
    inner: Any,
    inputs: list[str],
    memory_action: str | None,
) -> dict[str, Any]:
    """Build a log-safe embedding request body snapshot."""

    config = getattr(inner, "config", None)
    model = getattr(config, "model", None) or "(default)"
    body: dict[str, Any] = {
        "model": model,
        "encoding_format": "float",
        "memory_action": memory_action,
    }
    if len(inputs) == 1:
        body["input"] = text_for_log(inputs[0])
    else:
        body["input_count"] = len(inputs)
        body["input"] = [text_for_log(item) for item in inputs[:5]]
        if len(inputs) > 5:
            body["input_truncated"] = len(inputs) - 5
    embedding_dims = getattr(config, "embedding_dims", None)
    pass_dimensions = getattr(inner, "_pass_dimensions_to_api", False)
    if pass_dimensions and embedding_dims is not None:
        body["dimensions"] = embedding_dims
    return body


def summarize_embedding_vectors(vectors: list[list[float]]) -> dict[str, Any]:
    """Summarize embedding vectors for logs without dumping full arrays."""

    if not vectors:
        return {"data": [], "embedding_count": 0}
    data: list[dict[str, Any]] = []
    for index, vector in enumerate(vectors):
        item: dict[str, Any] = {"index": index, "embedding_dims": len(vector)}
        if vector:
            item["embedding_preview"] = [round(vector[0], 6), round(vector[-1], 6)]
        data.append(item)
    return {"embedding_count": len(vectors), "data": data}


def log_embedder_request(*, inner: Any, inputs: list[str], memory_action: str | None) -> None:
    """Emit INFO log for one embedder request."""

    url = embeddings_url_for(inner)
    body = build_embedder_request_body(inner=inner, inputs=inputs, memory_action=memory_action)
    details = format_log_kv(url=url, **body)
    if details:
        log.info("mem0 embedder request {}", details)
    else:
        log.info("mem0 embedder request")


def log_embedder_response(
    *,
    inner: Any,
    vectors: list[list[float]],
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit INFO log for one embedder response summary."""

    url = embeddings_url_for(inner)
    config = getattr(inner, "config", None)
    body = summarize_embedding_vectors(vectors)
    body["model"] = getattr(config, "model", None) or "(default)"
    if extra:
        body.update(extra)
    details = format_log_kv(url=url, **body)
    if details:
        log.info("mem0 embedder response {}", details)
    else:
        log.info("mem0 embedder response")


def make_probe_embedder_stand_in(*, base_url: str, model: str) -> Any:
    """Build a minimal embedder-like object for probe request logging."""

    return _ProbeEmbedderStandIn(base_url=base_url, model=model)


class _ProbeEmbedderStandIn:
    """Minimal stand-in so probe requests share embedder log formatting."""

    def __init__(self, *, base_url: str, model: str) -> None:
        """Store base URL and model for log URL/body construction."""

        self.config = type("_Cfg", (), {"model": model, "openai_base_url": base_url})()
        self._pass_dimensions_to_api = False


class LoggingEmbedderWrapper:
    """Delegate to mem0 embedder while logging request and response payloads."""

    def __init__(self, inner: Any) -> None:
        """Wrap an existing mem0 embedder instance."""

        self._inner = inner
        self.config = inner.config

    def embed(
        self,
        text: str,
        memory_action: Literal["add", "search", "update"] | None = None,
    ) -> list[float]:
        """Embed one text and log request/response summaries."""

        normalized = (text or "").replace("\n", " ")
        log_embedder_request(inner=self._inner, inputs=[normalized], memory_action=memory_action)
        vector = self._inner.embed(text, memory_action)
        log_embedder_response(inner=self._inner, vectors=[vector])
        return vector

    def embed_batch(self, texts: list[str], memory_action: str = "add") -> list[list[float]]:
        """Embed multiple texts and log one request/response pair per batch call."""

        normalized = [(item or "").replace("\n", " ") for item in texts]
        log_embedder_request(inner=self._inner, inputs=normalized, memory_action=memory_action)
        vectors = self._inner.embed_batch(texts, memory_action)
        log_embedder_response(inner=self._inner, vectors=vectors)
        return vectors

    def __getattr__(self, name: str) -> Any:
        """Forward unknown attributes to the wrapped embedder."""

        return getattr(self._inner, name)
