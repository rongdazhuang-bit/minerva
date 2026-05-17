"""Convert persisted agent messages into LangChain chat history for model calls."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.domain.db.models import AgentMessage


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
        if not content and role != "tool":
            continue
        if role == "user":
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
        return messages[:-1], None
    return messages, None


def messages_with_user_input(
    conversation_messages: list[BaseMessage],
    user_input: str,
) -> list[BaseMessage]:
    """Build model input: prior session turns plus one new user utterance."""

    prior, _ = split_trailing_user_message(conversation_messages)
    return [*prior, HumanMessage(content=user_input)]
