"""Volcengine vendor stub returning HTTP 501 until implemented."""

from __future__ import annotations

from app.ai_api.domain.models import ChatCallParams
from app.exceptions import AppError


class VolcenginePlaceholderStrategy:
    """Placeholder blocking/stream APIs until Volcengine wiring exists."""

    async def complete(self, params: ChatCallParams) -> dict[str, Any]:
        """Reject synchronously with ``AppError``."""

        raise AppError(
            "ai.provider.not_implemented",
            "Volcengine provider is not implemented yet.",
            501,
        )

    async def stream(self, params: ChatCallParams):
        """Reject streaming callers like ``complete``."""

        if False:  # pragma: no cover
            yield {}
        raise AppError(
            "ai.provider.not_implemented",
            "Volcengine provider is not implemented yet.",
            501,
        )
