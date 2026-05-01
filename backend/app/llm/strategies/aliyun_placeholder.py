"""Aliyun vendor stub returning HTTP 501 until implemented."""

from __future__ import annotations

from typing import Any

from app.llm.domain.models import ChatCallParams
from app.exceptions import AppError


class AliyunPlaceholderStrategy:
    """Placeholder blocking/stream APIs until Aliyun wiring exists."""

    async def complete(self, params: ChatCallParams) -> dict[str, Any]:
        """Reject synchronously with ``AppError``."""

        raise AppError(
            "ai.provider.not_implemented",
            "Aliyun provider is not implemented yet.",
            501,
        )

    async def stream(self, params: ChatCallParams):
        """Reject streaming callers like ``complete``."""

        if False:  # pragma: no cover
            yield {}
        raise AppError(
            "ai.provider.not_implemented",
            "Aliyun provider is not implemented yet.",
            501,
        )
