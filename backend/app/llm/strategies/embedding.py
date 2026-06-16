"""OpenAI Embeddings strategy."""

from __future__ import annotations

from typing import Any

from app.llm.domain.models import EmbeddingCallParams, EmbeddingResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import post_json, resolve_embeddings_url


class EmbeddingStrategy:
    """Concrete strategy for OpenAI-compatible embeddings."""

    async def embed(self, resolved: ResolvedModel, params: EmbeddingCallParams) -> EmbeddingResult:
        """Perform blocking embedding request."""

        body: dict[str, Any] = {
            "model": resolved.model_name,
            "input": params.input,
            "encoding_format": params.encoding_format,
        }
        if params.dimensions is not None:
            body["dimensions"] = params.dimensions
        raw = await post_json(
            url=resolve_embeddings_url(resolved.endpoint_url),
            api_key=resolved.api_key,
            body=body,
            log_label="embeddings",
        )
        return EmbeddingResult(
            data=list(raw.get("data") or []),
            model=raw.get("model"),
            usage=raw.get("usage"),
            raw=raw,
        )
