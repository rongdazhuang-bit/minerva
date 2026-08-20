"""Normalize MCP ``CallToolResult`` payloads into LLM-friendly text."""

from __future__ import annotations

import json
from typing import Any


def prettify_json_text(text: str) -> str:
    """If ``text`` looks like JSON, parse and re-serialize with indentation."""

    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return text
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def format_mcp_call_tool_result(result: Any) -> str:
    """Convert MCP ``CallToolResult`` to a single string for LangChain tool output."""

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False, indent=2)
    chunks: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(prettify_json_text(str(text)))
    return "\n".join(chunks) if chunks else str(result)
