"""Tests for agent session chat history conversion."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.infrastructure.chat_history import (
    agent_rows_to_langchain,
    messages_with_user_input,
    split_trailing_user_message,
)


def _row(*, role: str, content: str, seq: int) -> SimpleNamespace:
    return SimpleNamespace(
        role=role,
        content=content,
        seq=seq,
        tool_call_id=None,
    )


def test_agent_rows_to_langchain_maps_roles_and_trims() -> None:
    rows = [
        _row(role="user", content="列出公式", seq=1),
        _row(role="assistant", content="p=mv", seq=2),
        _row(role="user", content="给出第一个公式", seq=3),
    ]
    messages = agent_rows_to_langchain(rows, max_messages=2)
    assert len(messages) == 2
    assert isinstance(messages[0], AIMessage)
    assert messages[0].content == "p=mv"
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "给出第一个公式"


def test_split_trailing_user_message() -> None:
    prior, trailing = split_trailing_user_message(
        [AIMessage(content="p=mv"), HumanMessage(content="给出第一个公式")]
    )
    assert len(prior) == 1
    assert trailing == "给出第一个公式"


def test_messages_with_user_input_keeps_prior_turns() -> None:
    history = [
        HumanMessage(content="列出公式"),
        AIMessage(content="p=mv"),
        HumanMessage(content="给出第一个公式"),
    ]
    messages = messages_with_user_input(history, "根据上文回答第一个公式")
    assert len(messages) == 3
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "列出公式"
    assert messages[-1].content == "根据上文回答第一个公式"
