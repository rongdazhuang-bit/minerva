"""Runtime dependencies injected into graph nodes."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.run_db_writer import AgentRunDbWriter
from app.agent.memory.protocols import MemoryPersistStrategy, MemoryRetrieveStrategy
from app.agent.infrastructure.reasoning_collector import ReasoningCollector
from app.agent.infrastructure.openai_usage import (
    OpenAIUsage,
    extract_usage_document,
    extract_usage_from_langchain_output,
    merge_openai_usage,
    normalize_openai_usage,
    usage_document_flat,
)
from app.agent.infrastructure.usage_tracker import RunUsageTracker


SseEmitFn = Callable[[bytes], Awaitable[None]]


@dataclass
class GraphDeps:
    """Per-run services passed into compiled graph nodes."""

    db_writer: AgentRunDbWriter
    model: BaseChatModel
    workspace_id: uuid.UUID
    session_id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    memory_retrieve: MemoryRetrieveStrategy
    memory_persist: MemoryPersistStrategy
    # 单次 run 内缓冲思考流、发 SSE 并生成落库用的 reasoning 元数据；未开启 thinking 时为 None。
    reasoning_collector: ReasoningCollector | None = None
    emit_sse: SseEmitFn | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    conversation_messages: list[BaseMessage] | None = None
    subagent_cache: dict[tuple[str, str], CompiledStateGraph] = field(default_factory=dict)
    mcp_all_tools: list[Any] = field(default_factory=list)
    mcp_extra_tools: list[Any] = field(default_factory=list)
    mcp_bundles: list[Any] = field(default_factory=list)
    skip_memory: bool = False
    accumulated_usage: OpenAIUsage = field(default_factory=dict)
    usage_tracker: RunUsageTracker = field(default_factory=RunUsageTracker)
    _llm_round_seq: dict[uuid.UUID, int] = field(default_factory=dict)

    @asynccontextmanager
    async def db_write(self) -> AsyncIterator[AsyncSession]:
        """Short write transaction: commit on success, rollback on error."""

        async with self.db_writer.session() as session:
            yield session

    @asynccontextmanager
    async def db_read(self) -> AsyncIterator[AsyncSession]:
        """Short read-only session (always rolled back on exit)."""

        async with self.db_writer.session(read_only=True) as session:
            yield session

    def next_llm_round_seq(self, parent_node_id: uuid.UUID) -> int:
        """Return the next ``sequence_idx`` for ``llm.round`` rows under one parent node."""

        n = self._llm_round_seq.get(parent_node_id, 0)
        self._llm_round_seq[parent_node_id] = n + 1
        return n

    async def emit_llm_usage(
        self,
        raw_usage: Any,
        *,
        step_id: str | None = None,
        skill_id: str | None = None,
        phase: str | None = None,
        node_id: str | None = None,
    ) -> None:
        """Normalize, accumulate via ``usage_tracker``, and emit one ``llm.usage`` SSE event."""

        if node_id is None:
            if phase is None:
                usage = normalize_openai_usage(raw_usage)
                if not usage:
                    usage = extract_usage_from_langchain_output(raw_usage)
                if not usage:
                    return
                self.usage_tracker.flat_total = merge_openai_usage(
                    self.usage_tracker.flat_total, usage
                )
            else:
                usage_doc = self.usage_tracker.record_call(
                    raw_usage,
                    phase=phase,
                    step_id=step_id,
                    skill_id=skill_id,
                )
                if not usage_doc:
                    return
                usage = usage_document_flat(usage_doc)
        else:
            usage_doc = extract_usage_document(raw_usage)
            if not usage_doc:
                return
            usage = usage_document_flat(usage_doc)

        self.accumulated_usage = self.usage_tracker.flat_total
        if not self.emit_sse:
            return

        from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event

        payload: dict[str, Any] = {
            "usage": usage,
            "total_usage": dict(self.accumulated_usage),
        }
        if step_id is not None:
            payload["step_id"] = step_id
        if skill_id is not None:
            payload["skill_id"] = skill_id
        if phase is not None:
            payload["phase"] = phase
        if node_id is not None:
            payload["node_id"] = node_id

        await self.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.llm_usage,
                run_id=self.run_id,
                session_id=self.session_id,
                payload=payload,
            )
        )

    async def begin_llm_call_to_db(
        self,
        *,
        parent_node_id: uuid.UUID,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> uuid.UUID:
        """Insert ``llm.round`` (running) before an upstream LLM call."""

        seq = self.next_llm_round_seq(parent_node_id)
        node_id = uuid.uuid4()
        async with self.db_write() as session:
            await self.usage_tracker.begin_llm_round(
                session,
                node_id=node_id,
                run_id=self.run_id,
                parent_node_id=parent_node_id,
                sequence_idx=seq,
                phase=phase,
                step_id=step_id,
                skill_id=skill_id,
            )
        return node_id

    async def finalize_llm_call_to_db(
        self,
        node_id: uuid.UUID | None,
        raw_usage: Any,
        *,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
        status: str = "success",
        reasoning_text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Finalize ``llm.round`` and emit matching ``llm.usage`` SSE when applicable."""

        if node_id is None:
            return
        async with self.db_write() as session:
            await self.usage_tracker.finalize_llm_round(
                session,
                node_id=node_id,
                raw_usage=raw_usage,
                phase=phase,
                status=status,
                step_id=step_id,
                skill_id=skill_id,
                reasoning_text=reasoning_text,
                error_message=error_message,
            )
        if status == "success":
            await self.emit_llm_usage(
                raw_usage,
                step_id=step_id,
                skill_id=skill_id,
                phase=phase,
                node_id=str(node_id),
            )

    @asynccontextmanager
    async def llm_call_scope(
        self,
        *,
        parent_node_id: uuid.UUID,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> AsyncIterator[uuid.UUID]:
        """Begin ``llm.round``; finalize as ``failed`` if the wrapped block raises."""

        node_id = await self.begin_llm_call_to_db(
            parent_node_id=parent_node_id,
            phase=phase,
            step_id=step_id,
            skill_id=skill_id,
        )
        try:
            yield node_id
        except Exception as exc:
            await self.finalize_llm_call_to_db(
                node_id,
                {},
                phase=phase,
                step_id=step_id,
                skill_id=skill_id,
                status="failed",
                error_message=str(exc)[:500],
            )
            raise
