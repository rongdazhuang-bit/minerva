"""Workspace-scoped LLM chat completions with optional SSE streaming."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.llm.api.schemas import ChatCompletionRequest
from app.llm.domain.models import ChatMessage
from app.llm.service.chat_service import chat_service
from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User

router = APIRouter(
    prefix="/workspaces/{workspace_id}/llm",
    tags=["llm"],
)


def _to_chat_messages(body: ChatCompletionRequest) -> list[ChatMessage]:
    """Map inbound payload messages into domain ``ChatMessage`` rows."""

    return [ChatMessage(role=m.role, content=m.content) for m in body.messages]


@router.post("/chat/completions", response_model=None)
async def create_chat_completion(
    workspace_id: uuid.UUID,
    body: ChatCompletionRequest,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> dict[str, Any] | StreamingResponse:
    """Proxy unified chat completion to providers with optional streaming."""

    msgs = _to_chat_messages(body)
    if body.stream:
        return StreamingResponse(
            chat_service.stream_sse_lines(
                provider_kind=body.provider_kind,
                base_url=body.base_url,
                api_key=body.api_key,
                model=body.model,
                system_prompt=body.system_prompt,
                user_prompt=body.user_prompt,
                messages=msgs,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            ),
            media_type="text/event-stream",
        )
    return await chat_service.complete(
        provider_kind=body.provider_kind,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        system_prompt=body.system_prompt,
        user_prompt=body.user_prompt,
        messages=msgs,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )
