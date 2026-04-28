from __future__ import annotations

from typing import Any, AsyncIterator, Protocol

from app.ai_api.domain.models import ChatCallParams


class ChatCompletionStrategy(Protocol):
    async def complete(self, params: ChatCallParams) -> dict[str, Any]: ...

    def stream(self, params: ChatCallParams) -> AsyncIterator[dict[str, Any]]: ...
