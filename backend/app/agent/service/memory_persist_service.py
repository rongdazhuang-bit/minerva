"""Background long-term memory persistence after a successful agent run."""

from __future__ import annotations

import asyncio
import logging
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import AgentRun
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.openai_usage import (
    build_phase_delta,
    extract_usage_document,
    usage_document_for_node,
)
from app.agent.service.memory_extract_llm import invoke_memory_extract
from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.agent.infrastructure.memory_store import AgentMemoryStore
from app.core.infrastructure.db.session import async_session_factory

log = logging.getLogger(__name__)


async def persist_turn_memory(
    session: AsyncSession,
    *,
    model: BaseChatModel,
    memory_store: AgentMemoryStore,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    user_message: str,
    final_answer: str,
) -> None:
    """Extract summary/facts via LLM and write long-term memory rows."""

    final = (final_answer or "").strip()
    user_text = (user_message or "").strip()
    if not final:
        return

    node_id = uuid.uuid4()
    try:
        await agent_repo.insert_run_node(
            session,
            node_id=node_id,
            run_id=run_id,
            parent_node_id=None,
            sequence_idx=900,
            node_type="memory.persist",
            node_name="persist",
            status="running",
        )

        extract, raw_llm = await invoke_memory_extract(
            model,
            user_message=user_text,
            final_answer=final,
        )
        usage_doc = extract_usage_document(raw_llm)
        if usage_doc:
            await agent_repo.insert_run_node(
                session,
                node_id=uuid.uuid4(),
                run_id=run_id,
                parent_node_id=node_id,
                sequence_idx=0,
                node_type="llm.round",
                node_name="memory.persist",
                status="success",
                usage_json=usage_document_for_node(usage_doc),
                meta_json={"phase": "memory.persist"},
            )
            delta = build_phase_delta("memory.persist", usage_doc)
            await agent_repo.merge_run_usage_json(session, run_id=run_id, delta=delta)
            run_row = await session.get(AgentRun, run_id)
            if run_row is not None and isinstance(run_row.usage_json, dict):
                # Session 已在 Run finalize 时 merge 过主图用量；此处仅追加 memory.persist 增量。
                await agent_repo.merge_session_usage_json(
                    session,
                    session_id=session_id,
                    delta=delta,
                )
                await agent_repo.patch_assistant_message_usage_by_run(
                    session,
                    run_id=run_id,
                    usage_json=run_row.usage_json,
                )
            phase_slice = (delta.get("by_phase") or {}).get("memory.persist") or usage_document_for_node(
                usage_doc
            )
            await agent_repo.update_run_node_usage(
                session,
                node_id=node_id,
                usage_json=phase_slice,
            )
        summary = (extract.summary or final)[:2000]
        await memory_store.insert_summary(
            session,
            workspace_id=workspace_id,
            session_id=session_id,
            content=summary,
            source_run_id=run_id,
        )
        for fact in extract.facts[:5]:
            content = (fact.content or "").strip()
            if not content:
                continue
            await memory_store.upsert_fact(
                session,
                workspace_id=workspace_id,
                session_id=session_id,
                key=(fact.key or "").strip() or None,
                content=content[:2000],
                kind="fact",
                tags=fact.tags or None,
                source_run_id=run_id,
            )
        await memory_store.touch_session_summary(
            session, session_id=session_id, summary_text=summary[:8000]
        )
        await agent_repo.insert_run_node(
            session,
            node_id=uuid.uuid4(),
            run_id=run_id,
            parent_node_id=node_id,
            sequence_idx=0,
            node_type="memory.persist",
            node_name="done",
            status="success",
            outputs_json={"summary_chars": len(summary), "fact_count": len(extract.facts)},
        )
    except Exception as e:
        log.exception("memory.persist failed run_id=%s err=%s", run_id, e)


async def persist_turn_memory_background(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    user_message: str,
    final_answer: str,
    model_id: uuid.UUID,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> None:
    """Open a dedicated DB session and persist memory without blocking the SSE stream."""

    memory_store = AgentMemoryStore()
    async with async_session_factory() as session:
        try:
            model = await ChatModelFactory.get(
                session,
                workspace_id=workspace_id,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            await persist_turn_memory(
                session,
                model=model,
                memory_store=memory_store,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run_id,
                user_message=user_message,
                final_answer=final_answer,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            log.exception("memory.persist background failed run_id=%s", run_id)


def schedule_persist_turn_memory_background(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    user_message: str,
    final_answer: str,
    model_id: uuid.UUID,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> None:
    """Fire-and-forget background memory persist; logs task failures."""

    task = asyncio.create_task(
        persist_turn_memory_background(
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            user_message=user_message,
            final_answer=final_answer,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )

    def _done(t: asyncio.Task[None]) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log.error(
                "memory.persist background task crashed run_id=%s",
                run_id,
                exc_info=exc,
            )

    task.add_done_callback(_done)
