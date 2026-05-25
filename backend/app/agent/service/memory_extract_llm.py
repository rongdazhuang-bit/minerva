"""Invoke LLM for ``MemoryExtract`` with structured-output and parse fallbacks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.domain.memory_extract import MemoryExtract

log = logging.getLogger(__name__)

_MEMORY_EXTRACT_SYSTEM = """从本轮对话提取长期记忆，只输出一个 JSON 对象，不要 markdown 代码块，不要其它说明。
格式严格为：{"summary":"一句中文摘要","facts":[{"key":null,"content":"...","tags":[]}]}
facts 最多 5 条；无可复用事实时 facts 必须是空数组 []。"""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)
_SUMMARY_LINE_RE = re.compile(
    r"^\s*summary\s*[:：]\s*(.+?)(?:\s+facts\s*[:：]|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def fallback_memory_extract(user_message: str, final_answer: str) -> MemoryExtract:
    """Build a minimal extract when the model does not return parseable JSON."""

    user = (user_message or "").strip()[:240]
    snippet = " ".join((final_answer or "").split())[:600]
    if user and snippet:
        summary = f"用户：{user}；助手：{snippet}"
    else:
        summary = snippet or user or "本轮对话"
    return MemoryExtract(summary=summary[:2000], facts=[])


def parse_memory_extract_text(text: str) -> MemoryExtract | None:
    """Parse ``MemoryExtract`` from model text (JSON or loose ``summary:`` prefix)."""

    raw = (text or "").strip()
    if not raw:
        return None

    fence = _JSON_FENCE_RE.match(raw)
    if fence:
        raw = fence.group(1).strip()

    if raw.startswith("{"):
        try:
            return MemoryExtract.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            pass

    line_match = _SUMMARY_LINE_RE.match(raw)
    if line_match:
        return MemoryExtract(summary=line_match.group(1).strip()[:2000], facts=[])

    return None


def _extract_messages(user_message: str, final_answer: str) -> list[BaseMessage]:
    """Build chat messages for memory extraction."""

    return [
        SystemMessage(content=_MEMORY_EXTRACT_SYSTEM),
        HumanMessage(
            content=(
                f"用户：{(user_message or '').strip()}\n\n"
                f"助手：{(final_answer or '').strip()[:4000]}"
            )
        ),
    ]


async def invoke_memory_extract(
    model: BaseChatModel,
    *,
    user_message: str,
    final_answer: str,
) -> tuple[MemoryExtract, Any | None]:
    """Return ``(MemoryExtract, raw_llm_output)`` for usage tracking; never raises on format quirks."""

    messages = _extract_messages(user_message, final_answer)

    for method in ("json_schema", "function_calling"):
        try:
            runner = model.with_structured_output(MemoryExtract, method=method, include_raw=True)
            result = await runner.ainvoke(messages)
            if isinstance(result, dict):
                parsed = result.get("parsed")
                raw = result.get("raw")
                if isinstance(parsed, MemoryExtract):
                    return parsed, raw
            if isinstance(result, MemoryExtract):
                return result, result
        except Exception as exc:
            log.debug(
                "memory.extract structured method=%s failed: %s",
                method,
                exc,
            )

    try:
        resp = await model.ainvoke(messages)
        content = getattr(resp, "content", None)
        if isinstance(content, str):
            parsed = parse_memory_extract_text(content)
            if parsed is not None:
                return parsed, resp
    except Exception as exc:
        log.debug("memory.extract plain invoke failed: %s", exc)

    return fallback_memory_extract(user_message, final_answer), None
