"""Protocol describing completion strategies used by ``ChatService``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.ai_api.domain.models import ChatCallParams


class ChatCompletionStrategy(Protocol):
    """Provider-specific adapter implementing blocking and streaming completion."""

    async def complete(self, params: ChatCallParams) -> dict[str, Any]: ...

    def stream(self, params: ChatCallParams) -> AsyncIterator[dict[str, Any]]: ...
