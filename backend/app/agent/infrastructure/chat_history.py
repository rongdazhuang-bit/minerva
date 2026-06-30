"""Convert persisted agent messages into LangChain chat history for model calls."""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.domain.db.models import AgentMessage
from app.agent.infrastructure.vision_messages import (
    VisionAttachmentCache,
    build_vision_human_message,
)
from app.files.service.workspace_file_service import WorkspaceFileService


def _vision_attachments_from_list(attachments: list[dict]) -> list[dict]:
    """Keep only image attachments for vision message building."""

    out: list[dict] = []
    for item in attachments:
        kind = item.get("kind")
        if kind == "image":
            out.append(item)
            continue
        if kind == "file":
            continue
        mime = str(item.get("content_type") or "").strip().lower()
        if mime.startswith("image/"):
            out.append(item)
    return out


def _attachments_from_meta(meta_json: object) -> list[dict]:
    """Extract attachment dicts from one message ``meta_json``."""

    if not isinstance(meta_json, dict):
        return []
    raw = meta_json.get("attachments")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict) and item.get("object_key"):
            out.append(dict(item))
    return out


def agent_rows_to_langchain(
    rows: list[AgentMessage],
    *,
    max_messages: int,
) -> list[BaseMessage]:
    """Map DB rows to LangChain messages, keeping the most recent ``max_messages`` turns."""

    messages: list[BaseMessage] = []
    for row in rows:
        role = (row.role or "").strip().lower()
        content = (row.content or "").strip()
        attachments = _attachments_from_meta(row.meta_json)
        if not content and not attachments and role != "tool":
            continue
        if role == "user":
            if attachments:
                # Text-only fallback; vision rebuild happens in async builder.
                messages.append(HumanMessage(content=content or "[image]"))
            else:
                messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "tool" and row.tool_call_id:
            messages.append(ToolMessage(content=content, tool_call_id=row.tool_call_id))
    if max_messages > 0 and len(messages) > max_messages:
        return messages[-max_messages:]
    return messages


async def build_conversation_messages_for_run(
    rows: list[AgentMessage],
    *,
    workspace_id: uuid.UUID,
    file_service: WorkspaceFileService,
    cache: VisionAttachmentCache,
    include_vision_in_history: bool,
    max_messages: int,
    attachments_by_message_id: dict[uuid.UUID, list[dict]] | None = None,
) -> list[BaseMessage]:
    """Rebuild LangChain history, optionally embedding vision parts for user rows."""

    if max_messages > 0 and len(rows) > max_messages:
        rows = rows[-max_messages:]

    by_message = attachments_by_message_id or {}
    messages: list[BaseMessage] = []
    for row in rows:
        role = (row.role or "").strip().lower()
        content = (row.content or "").strip()
        attachments = by_message.get(row.id) or _attachments_from_meta(row.meta_json)
        vision_attachments = _vision_attachments_from_list(attachments)
        if not content and not attachments and role != "tool":
            continue
        if role == "user":
            msg = await build_vision_human_message(
                content,
                vision_attachments,
                workspace_id=workspace_id,
                file_service=file_service,
                cache=cache,
                include_images=include_vision_in_history and bool(vision_attachments),
            )
            messages.append(msg)
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "tool" and row.tool_call_id:
            messages.append(ToolMessage(content=content, tool_call_id=row.tool_call_id))
    return messages


def split_trailing_user_message(
    messages: list[BaseMessage],
) -> tuple[list[BaseMessage], str | None]:
    """Separate prior turns from the last user message when it is a ``HumanMessage``."""

    if not messages:
        return [], None
    last = messages[-1]
    if isinstance(last, HumanMessage):
        text = last.content
        if isinstance(text, str) and text.strip():
            return messages[:-1], text.strip()
        if isinstance(text, list):
            parts: list[str] = []
            for block in text:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            joined = "\n".join(p for p in parts if p).strip()
            if joined:
                return messages[:-1], joined
        return messages[:-1], None
    return messages, None


def messages_with_user_input(
    conversation_messages: list[BaseMessage],
    user_input: str,
) -> list[BaseMessage]:
    """Build model input: prior session turns plus one new user utterance."""

    prior, _ = split_trailing_user_message(conversation_messages)
    return [*prior, HumanMessage(content=user_input)]


async def messages_with_user_input_vision(
    conversation_messages: list[BaseMessage],
    user_input: str,
    attachments: list[dict],
    *,
    workspace_id: uuid.UUID,
    file_service: WorkspaceFileService,
    cache: VisionAttachmentCache,
    include_images: bool = True,
) -> list[BaseMessage]:
    """Build model input with optional vision attachments on the trailing user turn."""

    prior, _ = split_trailing_user_message(conversation_messages)
    vision_attachments = _vision_attachments_from_list(attachments)
    user_msg = await build_vision_human_message(
        user_input,
        vision_attachments,
        workspace_id=workspace_id,
        file_service=file_service,
        cache=cache,
        include_images=include_images and bool(vision_attachments),
    )
    return [*prior, user_msg]
