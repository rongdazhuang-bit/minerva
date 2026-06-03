"""SQL-backed memory persist strategy."""

from __future__ import annotations

from app.core.log import get_logger
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import AgentRun
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.memory_store import AgentMemoryStore
from app.agent.infrastructure.openai_usage import (
    build_phase_delta,
    extract_usage_document,
    usage_document_for_node,
)
from app.agent.service.memory_extract_llm import invoke_memory_extract

log = get_logger(__name__)


class SqlMemoryPersistStrategy:
    """Persist turn memory via LLM extract and ``agent_long_term_memory``."""

    def __init__(self, store: AgentMemoryStore | None = None) -> None:
        self._store = store or AgentMemoryStore()

    async def persist_turn(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        run_id: uuid.UUID,
        user_message: str,
        final_answer: str,
        model: BaseChatModel | None = None,
    ) -> None:
        """Extract summary/facts via LLM and write long-term memory rows."""

        if model is None:
            raise ValueError("SqlMemoryPersistStrategy requires model for LLM extract")

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
                await agent_repo.merge_run_usage_json(
                    session, run_id=run_id, delta=delta
                )
                run_row = await session.get(AgentRun, run_id)
                if run_row is not None and isinstance(run_row.usage_json, dict):
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
                phase_slice = (delta.get("by_phase") or {}).get(
                    "memory.persist"
                ) or usage_document_for_node(usage_doc)
                await agent_repo.update_run_node_usage(
                    session,
                    node_id=node_id,
                    usage_json=phase_slice,
                )
            summary = (extract.summary or final)[:2000]
            await self._store.insert_summary(
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
                await self._store.upsert_fact(
                    session,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    key=(fact.key or "").strip() or None,
                    content=content[:2000],
                    kind="fact",
                    tags=fact.tags or None,
                    source_run_id=run_id,
                )
            await self._store.touch_session_summary(
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
                outputs_json={
                    "summary_chars": len(summary),
                    "fact_count": len(extract.facts),
                },
            )
        except Exception as e:
            log.exception("memory.persist failed run_id={} err={}", run_id, e)
