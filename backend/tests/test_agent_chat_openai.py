"""Tests for AgentChatOpenAI reasoning preservation."""

from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from app.agent.infrastructure.agent_chat_openai import (
    AgentChatOpenAI,
    extract_reasoning_from_provider_payload,
)
from app.agent.infrastructure.reasoning_collector import extract_reasoning_from_langchain_message


def test_extract_reasoning_from_provider_payload_string_field() -> None:
    """DeepSeek-style reasoning_content is read from provider message dicts."""

    payload = {"role": "assistant", "content": "answer", "reasoning_content": "think"}
    assert extract_reasoning_from_provider_payload(payload) == "think"


def test_extract_reasoning_from_provider_payload_content_blocks() -> None:
    """Qwen-style thinking blocks inside content arrays are merged."""

    payload = {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "step1"},
            {"type": "text", "text": "answer"},
        ],
    }
    assert extract_reasoning_from_provider_payload(payload) == "step1"


def test_create_chat_result_attaches_reasoning_content() -> None:
    """Non-streaming responses copy provider reasoning into AIMessage additional_kwargs."""

    model = AgentChatOpenAI(model="test", api_key="k")
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "final",
                    "reasoning_content": "chain-of-thought",
                },
                "finish_reason": "stop",
            }
        ],
        "model": "test",
    }

    result = model._create_chat_result(response)

    assert isinstance(result.generations[0].message, AIMessage)
    assert result.generations[0].message.additional_kwargs["reasoning_content"] == "chain-of-thought"
    assert extract_reasoning_from_langchain_message(result.generations[0].message) == "chain-of-thought"


def test_convert_chunk_to_generation_chunk_attaches_streaming_reasoning() -> None:
    """Streaming deltas preserve reasoning_content for collectors and SSE mappers."""

    model = AgentChatOpenAI(model="test", api_key="k")
    chunk = {
        "choices": [
            {
                "delta": {
                    "role": "assistant",
                    "reasoning_content": "partial",
                },
                "finish_reason": None,
            }
        ],
        "model": "test",
    }

    generation_chunk = model._convert_chunk_to_generation_chunk(
        chunk,
        AIMessageChunk,
        {},
    )

    assert isinstance(generation_chunk, ChatGenerationChunk)
    assert generation_chunk.message.additional_kwargs["reasoning_content"] == "partial"


def test_create_chat_result_without_reasoning_is_unchanged() -> None:
    """Responses without provider reasoning behave like stock ChatOpenAI."""

    model = AgentChatOpenAI(model="test", api_key="k")
    response = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "only answer"},
                "finish_reason": "stop",
            }
        ],
        "model": "test",
    }

    result = model._create_chat_result(response)

    assert result.generations[0].message.content == "only answer"
    assert extract_reasoning_from_langchain_message(result.generations[0].message) == ""
