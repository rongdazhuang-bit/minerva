"""Track layered LLM token usage for a single agent run (memory + optional ``llm.round`` rows)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.openai_usage import (
    OpenAIUsage,
    UsageDocument,
    build_phase_delta,
    build_step_delta,
    extract_usage_document,
    merge_openai_usage,
    merge_usage_document,
    usage_document_flat,
    usage_document_for_node,
)


@dataclass
class RunUsageTracker:
    """In-memory layered totals for one run plus optional persistence of ``llm.round`` nodes."""

    document: UsageDocument = field(default_factory=dict)
    flat_total: OpenAIUsage = field(default_factory=dict)

    def record_call(
        self,
        raw_usage: Any,
        *,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> UsageDocument | None:
        """Accumulate one LLM call into the in-memory document (no database I/O)."""

        usage_doc = extract_usage_document(raw_usage)
        if not usage_doc:
            return None
        flat = usage_document_flat(usage_doc)
        self.flat_total = merge_openai_usage(self.flat_total, flat)
        delta = build_phase_delta(phase, usage_doc)
        if step_id and skill_id:
            step_doc = build_step_delta(step_id, skill_id, usage_doc)
            delta = merge_usage_document(delta, {"by_step": step_doc["by_step"]})
        self.document = merge_usage_document(self.document, delta)
        return usage_doc

    async def begin_llm_round(
        self,
        session: AsyncSession,
        *,
        node_id: uuid.UUID,
        run_id: uuid.UUID,
        parent_node_id: uuid.UUID | None,
        sequence_idx: int,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> uuid.UUID:
        """Insert ``llm.round`` in running state before the upstream LLM call."""

        meta: dict[str, Any] = {"phase": phase}
        if step_id is not None:
            meta["step_id"] = step_id
        if skill_id is not None:
            meta["skill_id"] = skill_id
        await agent_repo.begin_run_node(
            session,
            node_id=node_id,
            run_id=run_id,
            parent_node_id=parent_node_id,
            sequence_idx=sequence_idx,
            node_type="llm.round",
            node_name=phase,
            meta_json=meta,
        )
        return node_id

    async def finalize_llm_round(
        self,
        session: AsyncSession,
        *,
        node_id: uuid.UUID,
        raw_usage: Any,
        phase: str,
        status: str = "success",
        step_id: str | None = None,
        skill_id: str | None = None,
        reasoning_text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Finalize ``llm.round`` after the upstream LLM call returns or raises."""

        usage_doc = None
        if status == "success":
            usage_doc = self.record_call(
                raw_usage,
                phase=phase,
                step_id=step_id,
                skill_id=skill_id,
            )
        usage_payload = usage_document_for_node(usage_doc) if usage_doc else None
        await agent_repo.finalize_run_node(
            session,
            node_id=node_id,
            status=status,
            usage_json=usage_payload,
            reasoning_text=reasoning_text,
            error_message=error_message,
        )

    async def rollup_children(
        self,
        session: AsyncSession,
        *,
        node_id: uuid.UUID,
        child_usage: OpenAIUsage | UsageDocument,
    ) -> None:
        """Persist aggregated child usage onto a parent node's ``usage_json``."""

        payload: dict[str, Any]
        if isinstance(child_usage, dict) and (
            "prompt_tokens" in child_usage
            or "completion_tokens" in child_usage
            or "total_tokens" in child_usage
            or "details" in child_usage
        ):
            payload = usage_document_for_node(child_usage)
        else:
            payload = dict(child_usage)
        await agent_repo.update_run_node_usage(
            session,
            node_id=node_id,
            usage_json=payload,
        )

    def build_run_snapshot(self) -> UsageDocument:
        """Return the full layered document suitable for ``agent_run.usage_json``."""

        return dict(self.document)

    def build_session_delta(self) -> UsageDocument:
        """Return a snapshot without per-step buckets for merging into ``agent_session.usage_json``."""

        snap = self.build_run_snapshot()
        return {k: v for k, v in snap.items() if k != "by_step"}

