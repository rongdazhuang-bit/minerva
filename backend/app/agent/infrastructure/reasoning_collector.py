"""Accumulate streamed LLM reasoning, emit SSE v2 deltas, and build message payloads."""

from __future__ import annotations

import inspect
from typing import Any, Callable, TypedDict

from uuid import UUID

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.infrastructure.agent_chat_openai import extract_reasoning_from_provider_payload

# Visible planner / executor phases that surface in UI and persisted message metadata.
_VISIBLE_PHASES: frozenset[str] = frozenset({"planner", "subagent", "synthesizer"})


class ReasoningSegmentDict(TypedDict, total=False):
    """JSON-serializable segment entry for ``meta_json.reasoning``."""

    phase: str
    step_id: str | None
    skill_id: str | None
    text: str
    reasoning_tokens: int


def extract_reasoning_from_langchain_message(msg: Any) -> str:
    """Return reasoning text from LangChain ``additional_kwargs`` or structured content blocks."""

    kwargs = getattr(msg, "additional_kwargs", None)
    if isinstance(kwargs, dict):
        raw = kwargs.get("reasoning_content") or kwargs.get("reasoning")
        if raw is not None:
            return str(raw)
    content = getattr(msg, "content", None)
    if isinstance(content, list):
        return extract_reasoning_from_provider_payload({"content": content})
    return ""


def extract_reasoning_from_langchain_chunk(chunk: Any) -> str:
    """Return reasoning text from one streaming ``AIMessageChunk``."""

    return extract_reasoning_from_langchain_message(chunk)


def reasoning_tokens_from_raw(raw: Any) -> int:
    """Extract ``details.reasoning_tokens`` from a LangChain message or usage blob."""

    from app.agent.infrastructure.openai_usage import extract_usage_document, usage_document_flat

    doc = extract_usage_document(raw)
    if not doc:
        return 0
    flat = usage_document_flat(doc)
    details = flat.get("details") or {}
    value = details.get("reasoning_tokens")
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return 0


def _segment_key(
    phase: str,
    step_id: str | None,
    skill_id: str | None,
) -> tuple[str, str | None, str | None]:
    """Normalize storage key for one reasoning segment stream."""

    return (phase, step_id, skill_id)


def _reasoning_segment_header(
    phase: str,
    step_id: str | None,
    skill_id: str | None,
) -> str:
    """Human-readable banner for merged reasoning text (matches frontend segment titles)."""

    if phase == "planner":
        return "[Planner]"
    if phase == "synthesizer":
        return "[Synthesizer]"
    if phase == "subagent":
        sk = skill_id if skill_id is not None else "-"
        sid = step_id if step_id is not None else "-"
        return f"[{sk} · {sid}]"
    return f"[{phase}]"


class ReasoningCollector:
    """Buffers streamed reasoning deltas, forwards SSE lines, and materializes persistence shapes."""

    def __init__(
        self,
        run_id: UUID | str,
        session_id: UUID | str | None,
        emit_sse: Callable[[bytes], Any] | None,
        *,
        thinking_enabled: bool,
    ) -> None:
        """Attach stream context and optional emitter; disables all work when thinking is off."""

        self.run_id = run_id
        self.session_id = session_id
        self.emit_sse = emit_sse
        self.thinking_enabled = thinking_enabled

        self._buffers: dict[tuple[str, str | None, str | None], list[str]] = {}
        self._order: list[tuple[str, str | None, str | None]] = []
        self._reasoning_tokens: dict[tuple[str, str | None, str | None], int] = {}

    async def append_delta(
        self,
        phase: str,
        text: str,
        *,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> None:
        """Append one reasoning fragment, aggregate per segment, and emit ``llm.delta`` when enabled."""

        if not self.thinking_enabled or not text:
            return
        if phase not in _VISIBLE_PHASES:
            return
        key = _segment_key(phase, step_id, skill_id)
        if key not in self._order:
            self._order.append(key)
        self._buffers.setdefault(key, []).append(text)
        envelope = build_sse_event(
            event_type=AgentSseEventType.llm_delta,
            run_id=self.run_id,
            session_id=self.session_id,
            payload={
                "channel": "reasoning",
                "phase": phase,
                "step_id": step_id,
                "skill_id": skill_id,
                "text": text,
            },
        )
        await self._emit_sse(envelope)

    async def finalize_segment(
        self,
        phase: str,
        *,
        reasoning_tokens: int = 0,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> None:
        """Mark one segment complete and notify clients with ``llm.reasoning.segment_done``."""

        if not self.thinking_enabled:
            return
        if phase not in _VISIBLE_PHASES:
            return
        key = _segment_key(phase, step_id, skill_id)
        if key not in self._order:
            self._order.append(key)
        self._reasoning_tokens[key] = int(reasoning_tokens)
        envelope = build_sse_event(
            event_type=AgentSseEventType.llm_reasoning_segment_done,
            run_id=self.run_id,
            session_id=self.session_id,
            payload={
                "phase": phase,
                "step_id": step_id,
                "skill_id": skill_id,
                "reasoning_tokens": int(reasoning_tokens),
            },
        )
        await self._emit_sse(envelope)

    async def mark_all_done(self) -> None:
        """Emit ``llm.reasoning.done`` with the sum of per-segment ``reasoning_tokens``."""

        if not self.thinking_enabled:
            return
        total_tokens = sum(self._reasoning_tokens.values())
        envelope = build_sse_event(
            event_type=AgentSseEventType.llm_reasoning_done,
            run_id=self.run_id,
            session_id=self.session_id,
            payload={"reasoning_tokens": total_tokens},
        )
        await self._emit_sse(envelope)

    def build_message_reasoning(self) -> dict[str, Any] | None:
        """Produce ``meta_json.reasoning`` matching the agent reasoning spec, or None if empty/disabled."""

        if not self.thinking_enabled:
            return None

        segments: list[ReasoningSegmentDict] = []
        tokens_sum = 0

        for key in self._order:
            phase, sid, skid = key
            text = "".join(self._buffers.get(key, []))
            rt = int(self._reasoning_tokens.get(key, 0))
            tokens_sum += rt
            if not text and rt == 0:
                continue
            segments.append(
                {
                    "phase": phase,
                    "step_id": sid,
                    "skill_id": skid,
                    "text": text,
                    "reasoning_tokens": rt,
                },
            )

        if not segments:
            return None
        return {"segments": segments, "reasoning_tokens": tokens_sum}

    def build_message_reasoning_text(self) -> str | None:
        """Merge segment bodies with Planner / Subagent banners for plain-text DB storage."""

        if not self.thinking_enabled:
            return None

        parts: list[str] = []

        for key in self._order:
            phase, sid, skid = key
            text = "".join(self._buffers.get(key, []))
            rt = int(self._reasoning_tokens.get(key, 0))
            if not text and rt == 0:
                continue
            hdr = _reasoning_segment_header(phase, sid, skid)
            parts.append(f"{hdr}\n{text.strip()}")

        if not parts:
            return None
        return "\n\n".join(parts)

    async def _emit_sse(self, line: bytes) -> None:
        """Deliver one wire line when a consumer supplied ``emit_sse``."""

        emit = self.emit_sse
        if emit is None:
            return
        result = emit(line)
        if inspect.isawaitable(result):
            await result
