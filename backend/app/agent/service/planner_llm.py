"""Invoke LLM for ``Plan`` with structured-output and text-parse fallbacks."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.agent.domain.plan import Plan
from app.core.log import get_logger

log = get_logger(__name__)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)


def _message_content(raw: Any) -> str | None:
    """Extract string content from a LangChain message or structured raw payload."""

    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        joined = "\n".join(p for p in parts if p)
        return joined or None
    return None


def parse_plan_text(text: str) -> Plan | None:
    """Parse ``Plan`` from model text, tolerating markdown fences and leading noise (e.g. ``>``)."""

    raw = (text or "").strip()
    if not raw:
        return None

    fence = _JSON_FENCE_RE.match(raw)
    if fence:
        raw = fence.group(1).strip()

    payload = raw
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        payload = raw[start : end + 1]

    try:
        return Plan.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValueError):
        return None


def _coerce_structured_result(result: Any) -> tuple[Plan | None, Any | None]:
    """Normalize ``with_structured_output(..., include_raw=True)`` return value."""

    if isinstance(result, dict):
        parsed = result.get("parsed")
        raw = result.get("raw")
        if isinstance(parsed, Plan):
            return parsed, raw
        return None, raw
    if isinstance(result, Plan):
        return result, result
    return None, None


async def invoke_planner_plan(
    model: BaseChatModel,
    messages: list[BaseMessage],
) -> tuple[Plan | None, Any | None]:
    """Return ``(Plan, raw_llm_output)``; try structured methods then plain invoke + JSON parse."""

    for method in ("json_schema", "function_calling"):
        try:
            runner = model.with_structured_output(Plan, method=method, include_raw=True)
            result = await runner.ainvoke(messages)
            plan, raw = _coerce_structured_result(result)
            if plan is not None:
                return plan, raw
            text = _message_content(raw)
            if text:
                parsed = parse_plan_text(text)
                if parsed is not None:
                    return parsed, raw
        except Exception as exc:
            log.debug("planner structured method={} failed: {}", method, exc)

    try:
        resp = await model.ainvoke(messages)
        text = _message_content(resp)
        if text:
            parsed = parse_plan_text(text)
            if parsed is not None:
                return parsed, resp
    except Exception as exc:
        log.debug("planner plain invoke failed: {}", exc)

    return None, None
