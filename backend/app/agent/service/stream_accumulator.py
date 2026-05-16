"""Accumulate OpenAI-compatible streaming chunks into assistant text and ``tool_calls``."""

from __future__ import annotations

from typing import Any


class LlmStreamAccumulator:
    """合并上游 ``chat.completion.chunk`` 中的 ``delta``，产出完整 assistant 消息与 ``tool_calls``。"""

    def __init__(self) -> None:
        self._text_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._tool_calls: dict[int, dict[str, Any]] = {}
        self.finish_reason: str | None = None

    def feed(self, chunk: dict[str, Any]) -> None:
        """Record chunk state from one upstream ``chat.completion.chunk``."""

        choices = chunk.get("choices") or []
        if not choices:
            return
        c0 = choices[0]
        if not isinstance(c0, dict):
            return
        fr = c0.get("finish_reason")
        if fr:
            self.finish_reason = str(fr)
        delta = c0.get("delta") or {}
        if not isinstance(delta, dict):
            return
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._text_parts.append(content)
        reasoning = delta.get("reasoning_content")
        if not isinstance(reasoning, str) or not reasoning:
            reasoning = delta.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            self._reasoning_parts.append(reasoning)
        for tc in delta.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            idx = tc.get("index")
            if idx is None:
                continue
            i = int(idx)
            cur = self._tool_calls.setdefault(
                i,
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if tc.get("id"):
                cur["id"] = str(tc["id"])
            fn = tc.get("function") or {}
            if isinstance(fn, dict):
                if fn.get("name"):
                    cur["function"]["name"] = str(fn["name"])
                if fn.get("arguments"):
                    cur["function"]["arguments"] = str(cur["function"]["arguments"]) + str(fn["arguments"])

    def full_text(self) -> str:
        """Return concatenated assistant text seen so far."""

        return "".join(self._text_parts)

    def full_reasoning(self) -> str:
        """Return concatenated model reasoning tokens seen so far."""

        return "".join(self._reasoning_parts)

    def build_tool_calls_list(self) -> list[dict[str, Any]]:
        """Return ordered OpenAI ``tool_calls`` dicts (may be empty)."""

        return [self._tool_calls[k] for k in sorted(self._tool_calls)]

    def build_assistant_message_dict(self) -> dict[str, Any]:
        """Build a single ``assistant`` message dict for the next chat request."""

        text = self.full_text()
        tools = self.build_tool_calls_list()
        msg: dict[str, Any] = {"role": "assistant", "content": text if text else None}
        if tools:
            msg["tool_calls"] = tools
        return msg

    def build_meta_json(self) -> dict[str, Any] | None:
        """Optional ``meta_json`` for persistence (reasoning only when non-empty)."""

        reasoning = self.full_reasoning()
        if not reasoning:
            return None
        return {"reasoning": reasoning}
