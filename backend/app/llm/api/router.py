"""Workspace-scoped LLM proxy endpoints (chat, embeddings, rerank)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.llm.api.schemas import ChatCompletionRequest, EmbeddingRequest, RerankRequest
from app.llm.domain.models import ChatMessage, EmbeddingCallParams, RerankCallParams
from app.llm.domain.resolved_model import CHAT_MODEL_TAGS
from app.llm.service.llm_service import llm_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/llm",
    tags=["llm"],
)


def _to_chat_messages(body: ChatCompletionRequest) -> list[ChatMessage]:
    """Map inbound payload messages into domain ChatMessage rows."""

    return [ChatMessage(role=m.role, content=m.content) for m in body.messages]


@router.post("/chat/completions", response_model=None)
async def create_chat_completion(
    workspace_id: uuid.UUID,
    body: ChatCompletionRequest,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
):
    """Proxy chat completion via model_id with optional SSE streaming."""

    msgs = _to_chat_messages(body)
    if body.stream:
        return StreamingResponse(
            llm_service.stream_sse_lines(
                session,
                workspace_id=workspace_id,
                model_id=body.model_id,
                system_prompt=body.system_prompt,
                user_prompt=body.user_prompt,
                messages=msgs,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                top_p=body.top_p,
                n=body.n,
                stop=body.stop,
                presence_penalty=body.presence_penalty,
                frequency_penalty=body.frequency_penalty,
                allowed_tags=CHAT_MODEL_TAGS,
            ),
            media_type="text/event-stream",
        )
    result = await llm_service.complete_chat(
        session,
        workspace_id=workspace_id,
        model_id=body.model_id,
        system_prompt=body.system_prompt,
        user_prompt=body.user_prompt,
        messages=msgs,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        top_p=body.top_p,
        n=body.n,
        stop=body.stop,
        presence_penalty=body.presence_penalty,
        frequency_penalty=body.frequency_penalty,
        allowed_tags=CHAT_MODEL_TAGS,
    )
    return result.model_dump()


@router.post("/embeddings")
async def create_embedding(
    workspace_id: uuid.UUID,
    body: EmbeddingRequest,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
):
    """Proxy embedding call via model_id."""

    result = await llm_service.embed(
        session,
        workspace_id=workspace_id,
        model_id=body.model_id,
        params=EmbeddingCallParams(
            input=body.input,
            dimensions=body.dimensions,
            encoding_format=body.encoding_format,
        ),
    )
    return result.model_dump()


@router.post("/rerank")
async def create_rerank(
    workspace_id: uuid.UUID,
    body: RerankRequest,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
):
    """Proxy rerank call via model_id."""

    result = await llm_service.rerank(
        session,
        workspace_id=workspace_id,
        model_id=body.model_id,
        params=RerankCallParams(
            query=body.query,
            documents=body.documents,
            top_n=body.top_n,
        ),
    )
    return result.model_dump()
