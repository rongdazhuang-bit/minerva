from __future__ import annotations

from typing import Any

from app.ai_api.domain.models import ChatCallParams
from app.exceptions import AppError


class VolcenginePlaceholderStrategy:
    async def complete(self, params: ChatCallParams) -> dict[str, Any]:
        raise AppError(
            "ai.provider.not_implemented",
            "Volcengine provider is not implemented yet.",
            501,
        )

    async def stream(self, params: ChatCallParams):
        if False:  # pragma: no cover
            yield {}
        raise AppError(
            "ai.provider.not_implemented",
            "Volcengine provider is not implemented yet.",
            501,
        )
