"""Memory retrieve and persist graph nodes."""

from __future__ import annotations

import logging
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.domain.memory_extract import MemoryExtract
from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState

log = logging.getLogger(__name__)


async def memory_retrieve_node(state: AgentGraphState, config: dict) -> dict:
    """Load long-term memory hits into graph state."""

    deps: GraphDeps = config["configurable"]["deps"]
    hits = await deps.memory_store.retrieve(
        deps.db,
        workspace_id=deps.workspace_id,
        session_id=deps.session_id,
        query_text=state.get("user_message", ""),
    )
    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.memory_retrieved,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "hit_count": len(hits),
                    "sources": [h.source for h in hits[:5]],
                },
            )
        )
    return {"retrieved_memories": hits, "current_step_index": 0, "subagent_results": []}


async def memory_persist_node(state: AgentGraphState, config: dict) -> dict:
    """Extract summary/facts via LLM and persist to long-term memory."""

    deps: GraphDeps = config["configurable"]["deps"]
    final = (state.get("final_answer") or "").strip()
    user_message = (state.get("user_message") or "").strip()
    if not final:
        return {}

    node_id = uuid.uuid4()
    try:
        from app.agent.infrastructure import repository as agent_repo

        await agent_repo.insert_run_node(
            deps.db,
            node_id=node_id,
            run_id=deps.run_id,
            parent_node_id=None,
            sequence_idx=900,
            node_type="memory.persist",
            node_name="persist",
            status="running",
        )

        structured = deps.model.with_structured_output(MemoryExtract)
        extract: MemoryExtract = await structured.ainvoke(
            [
                SystemMessage(
                    content=(
                        "从本轮对话提取：一句 summary；0-5 条可复用 fact（含可选 key）。"
                        "无事实则 facts 为空列表。"
                    )
                ),
                HumanMessage(
                    content=f"用户：{user_message}\n\n助手：{final[:4000]}"
                ),
            ]
        )
        summary = (extract.summary or final)[:2000]
        await deps.memory_store.insert_summary(
            deps.db,
            workspace_id=deps.workspace_id,
            session_id=deps.session_id,
            content=summary,
            source_run_id=deps.run_id,
        )
        for fact in extract.facts[:5]:
            content = (fact.content or "").strip()
            if not content:
                continue
            await deps.memory_store.upsert_fact(
                deps.db,
                workspace_id=deps.workspace_id,
                session_id=deps.session_id,
                key=(fact.key or "").strip() or None,
                content=content[:2000],
                kind="fact",
                tags=fact.tags or None,
                source_run_id=deps.run_id,
            )
        await deps.memory_store.touch_session_summary(
            deps.db, session_id=deps.session_id, summary_text=summary[:8000]
        )
        await agent_repo.insert_run_node(
            deps.db,
            node_id=uuid.uuid4(),
            run_id=deps.run_id,
            parent_node_id=node_id,
            sequence_idx=0,
            node_type="memory.persist",
            node_name="done",
            status="success",
            outputs_json={"summary_chars": len(summary), "fact_count": len(extract.facts)},
        )
    except Exception as e:
        log.warning("memory.persist failed run_id=%s err=%s", deps.run_id, e)
        try:
            summary = final[:2000]
            await deps.memory_store.insert_summary(
                deps.db,
                workspace_id=deps.workspace_id,
                session_id=deps.session_id,
                content=summary,
                source_run_id=deps.run_id,
            )
            await deps.memory_store.touch_session_summary(
                deps.db, session_id=deps.session_id, summary_text=summary[:8000]
            )
        except Exception:
            pass
    return {}


def memory_context_text(state: AgentGraphState) -> str:
    """Format retrieved memories for planner prompts."""

    hits = state.get("retrieved_memories") or []
    if not hits:
        return ""
    lines = [f"- [{h.kind}/{h.source}] {h.content[:400]}" for h in hits[:10]]
    return "已知记忆：\n" + "\n".join(lines)
