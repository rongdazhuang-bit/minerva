"""Heuristics for when sub-agent output needs a synthesizer pass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.graphs.state import StepResult

# Process narration phrases — short closing lines that are not final reports.
_NARRATION_MARKERS: tuple[str, ...] = (
    "让我",
    "继续",
    "补充",
    "修正",
    "进一步",
    "现在查询",
    "已确认",
    "入手",
    "let me",
    "i'll",
    "i will",
)


@dataclass(frozen=True)
class SubagentRunStats:
    """Telemetry from one sub-agent ReAct run for synthesizer routing."""

    tool_call_count: int = 0
    last_ai_had_tool_calls: bool = False


def message_requested_tools(message: Any) -> bool:
    """Return True when a LangChain AI message includes pending tool calls."""

    if message is None:
        return False
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        return True
    extra = getattr(message, "additional_kwargs", None) or {}
    if isinstance(extra, dict) and extra.get("tool_calls"):
        return True
    return False


def looks_like_incomplete_narration(text: str) -> bool:
    """Return True when assistant text reads like mid-run narration, not a final report."""

    body = (text or "").strip()
    if not body:
        return True
    if len(body) < 120:
        return True
    if ("##" in body or "###" in body) and len(body) >= 400:
        return False
    if "对比" in body and len(body) >= 500:
        return False
    lowered = body.lower()
    return any(marker in body or marker in lowered for marker in _NARRATION_MARKERS)


def step_result_needs_synthesizer(result: StepResult) -> bool:
    """Return True when a step output should not be shown directly to the user."""

    tool_count = int(result.get("tool_call_count") or 0)
    if tool_count > 0:
        return True
    if result.get("last_ai_had_tool_calls"):
        return True
    output = (result.get("output") or "").strip()
    return looks_like_incomplete_narration(output)


def any_step_needs_synthesizer(results: list[StepResult]) -> bool:
    """Return True when at least one step requires a synthesizer pass."""

    return any(step_result_needs_synthesizer(r) for r in results)
