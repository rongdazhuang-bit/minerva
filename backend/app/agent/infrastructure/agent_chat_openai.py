"""Agent ChatOpenAI subclass that preserves third-party provider reasoning fields."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import openai
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


def extract_reasoning_from_provider_payload(payload: Mapping[str, Any]) -> str:
    """Extract reasoning text from an OpenAI-compatible message or streaming delta dict."""

    for key in ("reasoning_content", "reasoning"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw:
                if isinstance(item, str) and item:
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = (
                    item.get("text")
                    or item.get("content")
                    or item.get("reasoning")
                    or item.get("thinking")
                )
                if isinstance(text, str) and text:
                    parts.append(text)
            if parts:
                return "".join(parts)

    content = payload.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type not in ("thinking", "reasoning", "reasoning_content"):
                continue
            text = (
                block.get("thinking")
                or block.get("reasoning")
                or block.get("reasoning_content")
                or block.get("text")
                or block.get("content")
            )
            if isinstance(text, str) and text:
                parts.append(text)
        if parts:
            return "".join(parts)
    return ""


def _attach_reasoning_to_ai_message(message: Any, reasoning: str) -> None:
    """Merge provider reasoning into ``AIMessage.additional_kwargs`` without overwriting."""

    if not reasoning or not isinstance(message, (AIMessage, AIMessageChunk)):
        return
    kwargs = dict(getattr(message, "additional_kwargs", None) or {})
    existing = kwargs.get("reasoning_content") or kwargs.get("reasoning") or ""
    merged = f"{existing}{reasoning}" if existing else reasoning
    kwargs["reasoning_content"] = merged
    message.additional_kwargs = kwargs


class AgentChatOpenAI(ChatOpenAI):
    """``ChatOpenAI`` that keeps ``reasoning_content`` from non-OpenAI-compatible upstreams."""

    def _create_chat_result(
        self,
        response: dict | openai.BaseModel,
        generation_info: dict | None = None,
    ) -> ChatResult:
        """Preserve provider reasoning fields that upstream LangChain conversion drops."""

        result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}},
            )
        )
        for index, choice in enumerate(response_dict.get("choices") or []):
            message_dict = choice.get("message") or {}
            reasoning = extract_reasoning_from_provider_payload(message_dict)
            if not reasoning or index >= len(result.generations):
                continue
            _attach_reasoning_to_ai_message(result.generations[index].message, reasoning)
        return result

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        """Attach streaming reasoning deltas before LangGraph and collectors consume chunks."""

        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )
        if generation_chunk is None:
            return None
        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
        if not choices:
            return generation_chunk
        delta = choices[0].get("delta") or {}
        reasoning = extract_reasoning_from_provider_payload(delta)
        if reasoning:
            _attach_reasoning_to_ai_message(generation_chunk.message, reasoning)
        return generation_chunk
