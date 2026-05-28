"""OpenAI-compatible rerank strategy."""

from __future__ import annotations

from typing import Any

from app.llm.domain.models import RerankCallParams, RerankResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import post_json


class RerankStrategy:
    """Concrete strategy for OpenAI-compatible rerank APIs."""

    async def rerank(self, resolved: ResolvedModel, params: RerankCallParams) -> RerankResult:
        """Perform blocking rerank request."""

        body: dict[str, Any] = {
            "model": resolved.model_name,
            "query": params.query,
            "documents": params.documents,
        }
        if params.top_n is not None:
            body["top_n"] = params.top_n
        raw = await post_json(
            url=resolved.endpoint_url,
            api_key=resolved.api_key,
            body=body,
            log_label="rerank",
        )
        return RerankResult(
            id=raw.get("id"),
            results=list(raw.get("results") or []),
            raw=raw,
        )
